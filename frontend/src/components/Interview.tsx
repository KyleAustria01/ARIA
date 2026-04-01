import React, { useState, useRef, useEffect, useCallback } from "react";
import { useParams } from "react-router-dom";
import styles from "./Interview.module.css";

const API = {
  validateToken: (token: string) => fetch(`/api/applicant/validate-token/${token}`).then(r => r.json()),
  uploadResume: (token: string, file: File) => {
    const form = new FormData();
    form.append("token", token);
    form.append("file", file);
    return fetch("/api/applicant/upload-resume", {
      method: "POST",
      body: form
    }).then(r => r.json());
  }
};

const AVATAR = (
  <div className={styles.ariaAvatar}>
    <span role="img" aria-label="ARIA">🤖</span>
  </div>
);

const VerdictBadge = ({ verdict }: { verdict: string }) => {
  if (verdict === "Highly Recommended") return <span className={`${styles.verdictBadge} ${styles.badgeGreen}`}>{verdict}</span>;
  if (verdict === "Recommended") return <span className={`${styles.verdictBadge} ${styles.badgeYellow}`}>{verdict}</span>;
  return <span className={`${styles.verdictBadge} ${styles.badgeRed}`}>{verdict}</span>;
};

const Interview: React.FC = () => {
  const { token } = useParams<{ token: string }>();
  const [step, setStep] = useState<'pre_interview'|'interview'|'verdict'>('pre_interview');
  const [applicant, setApplicant] = useState<{name: string, role: string}|null>(null);
  const [resumeFile, setResumeFile] = useState<File|null>(null);
  const [resumeUploaded, setResumeUploaded] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string|null>(null);
  // wsRef lives at component top level — never has a stale-closure problem
  const wsRef = useRef<WebSocket|null>(null);
  const [ariaSpeaking, setAriaSpeaking] = useState(false);
  const [question, setQuestion] = useState<string>("");
  const [currentQuestion, setCurrentQuestion] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [recording, setRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob|null>(null);
  const [transcript, setTranscript] = useState<{q: string, a: string}[]>([]);
  const [verdict, setVerdict] = useState<any>(null);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string|null>(null);
  const mediaRecorder = useRef<MediaRecorder|null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const autoSubmitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const waveformRef = useRef<HTMLCanvasElement>(null);
  const recordingStartTime = useRef<number>(0);
  const [shortRecordingWarning, setShortRecordingWarning] = useState(false);



  // Validate token and get applicant info
  useEffect(() => {
    if (!token) return;
    API.validateToken(token).then(data => {
      if (data && data.valid) {
        setApplicant({ name: data.applicant_name, role: data.role });
      } else {
        setError("Invalid or expired invite link.");
      }
    }).catch(() => setError("Could not validate invite link."));
  }, [token]);

  // Resume upload
  const handleResumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setResumeFile(e.target.files[0]);
      setUploadError(null);
    }
  };
  const handleResumeDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setResumeFile(e.dataTransfer.files[0]);
      setUploadError(null);
    }
  };
  const handleResumeUpload = async () => {
    if (!resumeFile || !token) return;
    setUploading(true);
    setUploadError(null);
    try {
      const res = await API.uploadResume(token, resumeFile);
      if (res.status === "success") {
        setResumeUploaded(true);
      } else {
        setUploadError("Upload failed. Please try again.");
      }
    } catch {
      setUploadError("Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  // WebSocket interview flow
  // Audio queue for sequential playback
  const audioQueue = useRef<string[]>([]);
  const isPlaying = useRef(false);

  // playNextAudio uses refs only (empty dep array) — never captures stale state
  const playNextAudio = useCallback(() => {
    if (isPlaying.current || audioQueue.current.length === 0) return;
    isPlaying.current = true;
    const url = audioQueue.current.shift()!;
    const audio = new Audio(url);
    setStatus('aria_speaking');

    const handleDone = () => {
      isPlaying.current = false;
      URL.revokeObjectURL(url);
      if (audioQueue.current.length > 0) {
        playNextAudio();
      } else {
        // All audio finished — re-enable mic
        setStatus('recording_ready');
        setProcessing(false);
        // Always read the current ws from the ref, never from a closure
        const ws = wsRef.current;
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ready" }));
        }
      }
    };

    audio.onended = handleDone;
    audio.onerror = () => {
      console.error('Audio playback failed');
      handleDone();
    };
    audio.play().catch(() => {
      // Autoplay blocked or other failure — still enable the mic
      audio.onerror?.(new Event('error'));
    });
  }, []); // empty — relies solely on refs

  // Safety net: if status gets stuck on a non-interactive state for 30 s,
  // force-reset so the mic never remains permanently disabled.
  useEffect(() => {
    const STUCK_TIMEOUT = 30_000;
    if (status === 'aria_speaking' || status === 'processing') {
      const t = setTimeout(() => {
        console.warn('[ARIA] Status stuck on', status, '— force resetting to recording_ready');
        setStatus('recording_ready');
        setProcessing(false);
      }, STUCK_TIMEOUT);
      return () => clearTimeout(t);
    }
  }, [status]);

  useEffect(() => {
    if (step !== 'interview') return;
    // Avoid re-connecting if already open
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;
    if (!token) return;

    const wsBase = import.meta.env.VITE_WS_URL || `ws://localhost:8000`;
    const socket = new window.WebSocket(`${wsBase}/ws/interview/${token}`);
    wsRef.current = socket;

    socket.onopen = () => {
      setStatus('Connecting...');
      // Send start signal immediately — no identity check needed
      socket.send(JSON.stringify({ type: 'start' }));
    };

    socket.onmessage = async (event) => {
      // Binary = audio from ARIA
      if (event.data instanceof Blob) {
        const url = URL.createObjectURL(event.data);
        audioQueue.current.push(url);
        playNextAudio();
        return;
      }

      // JSON messages
      try {
        const msg = JSON.parse(event.data);
        console.log('WS message:', msg);

        switch (msg.type) {
          case 'transcript':
            if (msg.role === 'aria') {
              setQuestion(msg.text);
              setCurrentQuestion(msg.text);
              setStatus('aria_speaking');
              setAriaSpeaking(true);
            } else {
              setTranscript(t => [...t, { q: currentQuestion, a: msg.text }]);
            }
            break;

          case 'thinking':
            setStatus('processing');
            setProcessing(true);
            break;

          case 'checkin':
            setStatus('recording_ready');
            break;

          case 'resume':
            // Restore transcript from resumed session
            if (msg.conversation_history) {
              const restored: {q: string, a: string}[] = [];
              let lastQ = '';
              for (const turn of msg.conversation_history) {
                if (turn.role === 'aria') lastQ = turn.text;
                else restored.push({ q: lastQ, a: turn.text });
              }
              setTranscript(restored);
            }
            setStatus('aria_speaking');
            break;

          case 'verdict':
            setVerdict(msg.data || msg.text);
            setStatus('complete');
            setStep('verdict');
            break;

          case 'error':
            setError(msg.text || msg.message);
            break;

          case 'timeout':
            setError(msg.text);
            break;

          case 'debug':
            // Development-only state snapshots — ignore in UI
            break;

          default:
            console.log('Unknown WS message type:', msg.type);
        }
      } catch (e) {
        console.error('Failed to parse WS message:', e);
      }
    };

    socket.onerror = () => setError('WebSocket error. Please refresh.');
    socket.onclose = () => {};

    return () => { socket.close(); wsRef.current = null; };
    // eslint-disable-next-line
  }, [step, token]);

  // TTS playback
  const playTTS = async (text: string) => {
    try {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text })
      });
      if (!res.ok) return;
      const audioData = await res.arrayBuffer();
      const audio = new Audio(URL.createObjectURL(new Blob([audioData], { type: 'audio/mpeg' })));
      await audio.play();
    } catch {}
  };

  // Audio recording
  const startRecording = async () => {
    try {
      setRecording(true);
      setAudioBlob(null);
      audioChunks.current = [];
      setStatus('recording');
      setShortRecordingWarning(false);
      recordingStartTime.current = Date.now();

      // Notify backend: applicant started speaking — pause check-in timer
      wsRef.current?.send(JSON.stringify({ type: "recording_started" }));

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm'
      });
      mediaRecorder.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.current.push(e.data);
      };

      recorder.onstop = () => {
        const blob = new Blob(audioChunks.current, { type: 'audio/webm' });
        stream.getTracks().forEach(track => track.stop());
        const durationMs = Date.now() - recordingStartTime.current;

        // If recording < 2 seconds — likely accidental stop, don't auto-submit
        if (durationMs < 2000) {
          setAudioBlob(blob);
          setStatus('recording_ready');
          setShortRecordingWarning(true);
          setTimeout(() => setShortRecordingWarning(false), 5000);
          return;
        }

        // Brief review window before auto-submit
        setAudioBlob(blob);
        setStatus('review');

        // Auto-submit after 1.5 s — user can cancel during this window
        autoSubmitTimer.current = setTimeout(() => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            setProcessing(true);
            setStatus('processing');
            wsRef.current.send(JSON.stringify({ type: "recording_stopped" }));
            setTimeout(() => {
              wsRef.current?.send(blob);
              setAudioBlob(null);
            }, 100);
          }
        }, 1500);
      };

      recorder.start(250); // collect in 250 ms chunks
    } catch (err) {
      console.error('Recording failed:', err);
      setRecording(false);
      setStatus('recording_ready');
    }
  };

  const stopRecording = () => {
    setRecording(false);
    mediaRecorder.current?.stop();
    // Status stays as-is until onstop fires and sets 'review'
  };

  // Send audio to backend manually (used when auto-submit is cancelled and re-triggered)
  const handleSubmitAnswer = () => {
    if (!wsRef.current || !audioBlob) return;
    if (autoSubmitTimer.current) {
      clearTimeout(autoSubmitTimer.current);
      autoSubmitTimer.current = null;
    }
    setProcessing(true);
    setStatus('processing');
    wsRef.current.send(JSON.stringify({ type: "recording_stopped" }));
    setTimeout(() => {
      wsRef.current?.send(audioBlob!);
      setAudioBlob(null);
    }, 100);
  };

  const cancelAutoSubmit = () => {
    if (autoSubmitTimer.current) {
      clearTimeout(autoSubmitTimer.current);
      autoSubmitTimer.current = null;
    }
    setAudioBlob(null);
    setStatus('recording_ready');
  };

  // Drag and drop events
  const preventDefaults = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  // Render
  if (error) {
    return <div className={styles.interviewRoot}><div className={styles.welcomeCard}><h2>Error</h2><div>{error}</div></div></div>;
  }

  if (step === 'pre_interview' && applicant) {
    return (
      <div className={styles.interviewRoot}>
        {AVATAR}
        <div className={styles.welcomeCard}>
          <h2>Welcome, {applicant.name}!</h2>
          <div className={styles.role}>Role: {applicant.role}</div>
          <div
            className={resumeUploaded ? styles.resumeUpload + ' ' + styles.resumeUploaded : styles.resumeUpload}
            onDrop={handleResumeDrop}
            onDragOver={preventDefaults}
            onDragEnter={preventDefaults}
            onDragLeave={preventDefaults}
          >
            <div className={styles.uploadLabel}>Upload your Resume (PDF)</div>
            <input type="file" accept="application/pdf" style={{ display: 'none' }} id="resumeInput" onChange={handleResumeChange} />
            <label htmlFor="resumeInput" className={styles.uploadBtn} style={{ marginBottom: 0 }}>Browse</label>
            {resumeFile && <div className={styles.fileName}>{resumeFile.name}</div>}
            <button className={styles.uploadBtn} onClick={handleResumeUpload} disabled={!resumeFile || uploading || resumeUploaded} type="button">
              {uploading ? "Uploading..." : resumeUploaded ? "Uploaded" : "Upload"}
            </button>
            {resumeUploaded && <div className={styles.successCheck}>✔️</div>}
            {uploadError && <div style={{ color: '#f87171', marginTop: 8 }}>{uploadError}</div>}
          </div>
          <button className={styles.startBtn} disabled={!resumeUploaded} onClick={() => setStep('interview')}>Start Interview</button>
          <button className={styles.startBtn} onClick={() => setStep('interview')} style={{ marginTop: 8, opacity: resumeUploaded ? 0 : 0.7 }}>
            {resumeUploaded ? '' : 'Skip Resume & Start'}
          </button>
        </div>
      </div>
    );
  }
  if (step === 'interview') {
    return (
      <div className={styles.interviewRoot}>
        <div className={ariaSpeaking ? styles.ariaAvatar + ' ' + styles.ariaSpeaking : styles.ariaAvatar}>{AVATAR.props.children}</div>
        <div className={styles.interviewCard}>
          <div className={styles.question}>{question}</div>
          <div className={styles.status}>
            {status === 'aria_speaking' && 'ARIA is speaking...'}
            {status === 'recording_ready' && 'Your turn — press mic to answer'}
            {status === 'recording' && 'Recording... click to stop'}
            {status === 'review' && 'Answer recorded'}
            {status === 'processing' && 'Processing your answer...'}
            {status === 'ARIA is thinking...' && 'ARIA is thinking...'}
            {status === 'Still processing, please wait...' && 'Still processing, please wait...'}
            {status === 'complete' && 'Interview complete.'}
            {![
              'aria_speaking',
              'recording_ready',
              'recording',
              'review',
              'processing',
              'ARIA is thinking...',
              'Still processing, please wait...',
              'complete'
            ].includes(status) && status}
          </div>
          <button
            className={recording ? styles.micBtn + ' ' + styles.micRecording : styles.micBtn + ' ' + styles.micIdle}
            onClick={recording ? stopRecording : startRecording}
            disabled={status !== 'recording_ready' && status !== 'recording'}
            title={
              status === 'aria_speaking'
                ? 'Wait for ARIA to finish speaking'
                : status === 'processing'
                ? 'Processing your answer...'
                : status === 'review'
                ? 'Answer recorded — sending shortly'
                : 'Press to record your answer'
            }
            aria-label={recording ? "Stop recording" : "Start recording"}
          >
            <span role="img" aria-label="mic">🎤</span>
          </button>
          {recording && <div className={styles.waveform}>[Waveform]</div>}

          {/* Auto-submit review bar */}
          {status === 'review' && (
            <div className={styles.autoSubmitBar}>
              <span>Sending answer in 1.5 s…</span>
              <button className={styles.cancelBtn} onClick={cancelAutoSubmit}>
                Cancel &amp; Re-record
              </button>
            </div>
          )}

          {/* Short recording warning */}
          {shortRecordingWarning && audioBlob && (
            <div className={styles.shortWarning}>
              <span>⚠️ Recording was very short. Done or re-record?</span>
              <button className={styles.submitBtn} onClick={handleSubmitAnswer}>Submit Answer</button>
              <button className={styles.cancelBtn} onClick={() => { setShortRecordingWarning(false); setAudioBlob(null); startRecording(); }}>Record Again</button>
            </div>
          )}

          {/* Manual submit — only shown if review state was cancelled and blob still present */}
          {audioBlob && status === 'recording_ready' && !shortRecordingWarning && (
            <button className={styles.submitBtn} onClick={handleSubmitAnswer} disabled={processing}>Submit</button>
          )}
        </div>
        {transcript.length > 0 && (
          <div className={styles.transcript}>
            {transcript.map((t, i) => (
              <div key={i}><span className={styles.transcriptQ}>Q:</span> {t.q}<br /><span className={styles.transcriptA}>A:</span> {t.a}</div>
            ))}
          </div>
        )}
      </div>
    );
  }
  if (step === 'verdict' && verdict) {
    const score = verdict.technical_score || 0;
    const badge = verdict.recommendation || "Not Recommended";
    return (
      <div className={styles.interviewRoot}>
        <div className={styles.verdictCard}>
          <div className={styles.verdictHeading}>Interview Complete</div>
          <VerdictBadge verdict={badge} />
          <div className={styles.scoreBar}>
            <div className={styles.scoreFill} style={{ width: `${score * 10}%` }}></div>
          </div>
          <div>Technical Score: {score}/10</div>
          <div className={styles.strengths}>
            <div className={styles.sectionTitle}>Strengths</div>
            <ul>{(verdict.strengths || []).map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>
          </div>
          <div className={styles.concerns}>
            <div className={styles.sectionTitle}>Areas of Concern</div>
            <ul>{(verdict.concerns || []).map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>
          </div>
          <div className={styles.hiringRec}>{verdict.hiring_recommendation || ""}</div>
        </div>
      </div>
    );
  }
  return <div className={styles.interviewRoot}><div className={styles.welcomeCard}>Loading...</div></div>;
};

export default Interview;
