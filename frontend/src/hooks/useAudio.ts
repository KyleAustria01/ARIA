import { useCallback, useRef, useState } from "react";

interface UseAudioReturn {
  isRecording: boolean;
  isPlaying: boolean;
  /** Mic input level 0-1 (updated ~30 fps while recording). */
  audioLevel: number;
  startRecording: (onStop?: (buffer: ArrayBuffer) => void) => Promise<void>;
  stopRecording: () => void;
  playAudio: (buffer: ArrayBuffer) => Promise<void>;
  /** Immediately stop all audio playback and recording. */
  stopAll: () => void;
}

export function useAudio(): UseAudioReturn {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<AudioBufferSourceNode | null>(null);
  const onStopRef = useRef<((buffer: ArrayBuffer) => void) | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const levelCtxRef = useRef<AudioContext | null>(null);
  const levelRafRef = useRef<number>(0);

  const [isRecording, setIsRecording] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);

  const startRecording = useCallback(
    async (onStop?: (buffer: ArrayBuffer) => void) => {
      if (isRecording) return;
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      onStopRef.current = onStop ?? null;

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
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        // Tear down analyser
        cancelAnimationFrame(levelRafRef.current);
        try { levelCtxRef.current?.close(); } catch { /* */ }
        analyserRef.current = null;
        levelCtxRef.current = null;
        setAudioLevel(0);

        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        const buffer = await blob.arrayBuffer();
        onStopRef.current?.(buffer);
        // Stop all mic tracks to release the microphone
        stream.getTracks().forEach((t) => t.stop());
        setIsRecording(false);
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
    },
    [isRecording]
  );

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
  }, []);

  const playAudio = useCallback(async (buffer: ArrayBuffer): Promise<void> => {
    if (!audioCtxRef.current || audioCtxRef.current.state === "closed") {
      audioCtxRef.current = new AudioContext();
    }
    const ctx = audioCtxRef.current;
    try {
      setIsPlaying(true);
      const decoded = await ctx.decodeAudioData(buffer.slice(0));
      const source = ctx.createBufferSource();
      source.buffer = decoded;
      source.connect(ctx.destination);
      source.onended = () => {
        sourceRef.current = null;
        setIsPlaying(false);
      };
      sourceRef.current = source;
      source.start(0);
    } catch {
      setIsPlaying(false);
    }
  }, []);

  const stopAll = useCallback(() => {
    // Stop any active playback
    try { sourceRef.current?.stop(); } catch { /* already stopped */ }
    sourceRef.current = null;
    // Close the AudioContext so queued audio is discarded
    try { audioCtxRef.current?.close(); } catch { /* ignore */ }
    audioCtxRef.current = null;
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
    setIsRecording(false);
  }, []);

  return { isRecording, isPlaying, audioLevel, startRecording, stopRecording, playAudio, stopAll };
}

