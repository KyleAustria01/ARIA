import { useCallback, useRef, useState } from "react";

interface UseAudioReturn {
  isRecording: boolean;
  isPlaying: boolean;
  /** Mic input level 0-1 (updated ~30 fps while recording). */
  audioLevel: number;
  startRecording: (onChunk?: (buffer: ArrayBuffer) => void) => Promise<void>;
  /** Stop recording and return the recorded audio blob */
  stopRecording: () => Promise<Blob | null>;
  playAudio: (buffer: ArrayBuffer) => Promise<void>;
  /** Immediately stop all audio playback and recording. */
  stopAll: () => void;
}

export function useAudio(): UseAudioReturn {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const blobUrlRef = useRef<string | null>(null);
  const onChunkRef = useRef<((buffer: ArrayBuffer) => void) | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const levelCtxRef = useRef<AudioContext | null>(null);
  const levelRafRef = useRef<number>(0);
  const streamRef = useRef<MediaStream | null>(null);
  const stopResolverRef = useRef<((blob: Blob | null) => void) | null>(null);

  const [isRecording, setIsRecording] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);

  const startRecording = useCallback(
    async (onChunk?: (buffer: ArrayBuffer) => void) => {
      if (isRecording) return;
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      onChunkRef.current = onChunk ?? null;

      // Set up AnalyserNode for live mic level
      const lCtx = new AudioContext();
      const src = lCtx.createMediaStreamSource(stream);
      const analyser = lCtx.createAnalyser();
      analyser.fftSize = 256;
      src.connect(analyser);
      analyserRef.current = analyser;
      levelCtxRef.current = lCtx;
      const buf = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) sum += buf[i];
        setAudioLevel(sum / buf.length / 255);
        levelRafRef.current = requestAnimationFrame(tick);
      };
      levelRafRef.current = requestAnimationFrame(tick);

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
          // If streaming chunks (for WebSocket), send each chunk
          if (onChunkRef.current) {
            e.data.arrayBuffer().then((buf) => onChunkRef.current?.(buf));
          }
        }
      };

      recorder.onstop = async () => {
        // Tear down analyser
        cancelAnimationFrame(levelRafRef.current);
        try { levelCtxRef.current?.close(); } catch { /* */ }
        analyserRef.current = null;
        levelCtxRef.current = null;
        setAudioLevel(0);

        try {
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          // Resolve the stopRecording promise with the blob
          stopResolverRef.current?.(blob);
        } catch (err) {
          console.error("[useAudio] onstop error:", err);
          stopResolverRef.current?.(null);
        } finally {
          // Always release mic and reset state
          streamRef.current?.getTracks().forEach((t) => t.stop());
          streamRef.current = null;
          stopResolverRef.current = null;
          setIsRecording(false);
        }
      };

      recorder.onerror = () => {
        cancelAnimationFrame(levelRafRef.current);
        try { levelCtxRef.current?.close(); } catch { /* */ }
        analyserRef.current = null;
        levelCtxRef.current = null;
        setAudioLevel(0);
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        stopResolverRef.current?.(null);
        stopResolverRef.current = null;
        setIsRecording(false);
      };

      recorder.start(250); // Collect data every 250ms for streaming
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
    },
    [isRecording]
  );

  const stopRecording = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      if (mediaRecorderRef.current?.state === "recording") {
        stopResolverRef.current = resolve;
        mediaRecorderRef.current.stop();
      } else {
        resolve(null);
      }
    });
  }, []);

  const playAudio = useCallback(async (buffer: ArrayBuffer): Promise<void> => {
    console.log("[useAudio] playAudio called, buffer size:", buffer.byteLength);
    // Clean up previous playback
    if (audioElRef.current) {
      audioElRef.current.pause();
      audioElRef.current = null;
    }
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current);
      blobUrlRef.current = null;
    }

    // Detect MIME: MP3 starts with 0xFF 0xFB/0xF3/0xF2 or ID3 tag
    const header = new Uint8Array(buffer.slice(0, 3));
    const isMP3 = (header[0] === 0xFF && (header[1] & 0xE0) === 0xE0) ||
                  (header[0] === 0x49 && header[1] === 0x44 && header[2] === 0x33); // "ID3"
    const mime = isMP3 ? "audio/mpeg" : "audio/wav";
    console.log("[useAudio] detected MIME:", mime, "header bytes:", Array.from(header));

    const blob = new Blob([buffer], { type: mime });
    const url = URL.createObjectURL(blob);
    blobUrlRef.current = url;

    const audio = new Audio(url);
    audioElRef.current = audio;

    return new Promise<void>((resolve) => {
      setIsPlaying(true);
      let resolved = false;

      const done = () => {
        if (resolved) return;
        resolved = true;
        clearTimeout(safetyTimer);
        setIsPlaying(false);
        audioElRef.current = null;
        URL.revokeObjectURL(url);
        blobUrlRef.current = null;
        resolve();
      };

      // Safety: force-resolve if audio doesn't end within 30 s
      const safetyTimer = setTimeout(() => {
        console.warn("[useAudio] playAudio safety timeout — forcing resolve");
        done();
      }, 30_000);

      audio.onended = done;
      audio.onerror = done;
      audio.play().catch(done);
    });
  }, []);

  const stopAll = useCallback(() => {
    // Stop any active playback
    if (audioElRef.current) {
      audioElRef.current.pause();
      audioElRef.current = null;
    }
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current);
      blobUrlRef.current = null;
    }
    setIsPlaying(false);
    // Tear down analyser
    cancelAnimationFrame(levelRafRef.current);
    try { levelCtxRef.current?.close(); } catch { /* */ }
    analyserRef.current = null;
    levelCtxRef.current = null;
    setAudioLevel(0);
    // Stop any active recording
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    // Clean up stream
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    stopResolverRef.current?.(null);
    stopResolverRef.current = null;
    setIsRecording(false);
  }, []);

  return { isRecording, isPlaying, audioLevel, startRecording, stopRecording, playAudio, stopAll };
}

