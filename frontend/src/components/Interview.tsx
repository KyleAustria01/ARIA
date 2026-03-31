import React, { useState, useRef, useEffect } from "react";
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
  const [step, setStep] = useState<'welcome'|'interview'|'verdict'>('welcome');
  const [applicant, setApplicant] = useState<{name: string, role: string}|null>(null);
  const [resumeFile, setResumeFile] = useState<File|null>(null);
  const [resumeUploaded, setResumeUploaded] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string|null>(null);
  const [ws, setWs] = useState<WebSocket|null>(null);
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
  const waveformRef = useRef<HTMLCanvasElement>(null);

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
  const playNextAudio = () => {
    if (isPlaying.current || audioQueue.current.length === 0) return;
    isPlaying.current = true;
    const url = audioQueue.current.shift()!;
    const audio = new Audio(url);
    setStatus('aria_speaking');
    audio.onended = () => {
      isPlaying.current = false;
      URL.revokeObjectURL(url);
      if (audioQueue.current.length > 0) {
        playNextAudio();
      } else {
        setStatus('recording_ready');
        setProcessing(false);
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "ready" }));
        }
      }
    };
    audio.play();
  };

  useEffect(() => {
    if (step !== 'interview' || !token) return;
    const socket = new window.WebSocket(`ws://localhost:8000/ws/interview/${token}`);
    setWs(socket);
    wsRef.current = socket;
    let llmTimeout: NodeJS.Timeout | null = null;
    let llmLongTimeout: NodeJS.Timeout | null = null;
    const clearLLMTimers = () => {
      if (llmTimeout) clearTimeout(llmTimeout);
      if (llmLongTimeout) clearTimeout(llmLongTimeout);
      llmTimeout = null;
      llmLongTimeout = null;
    };
    socket.onopen = () => {
      setStatus("ARIA is speaking...");
    };
    socket.onmessage = async (event) => {
      // Binary = audio from ARIA
      if (event.data instanceof Blob) {
        clearLLMTimers();
        const url = URL.createObjectURL(event.data);
        audioQueue.current.push(url);
        playNextAudio();
        return;
      }

      // JSON = question, transcript, verdict
      const msg = JSON.parse(event.data);
      console.log('WS message:', msg);

      if (msg.type === 'welcome') {
        clearLLMTimers();
        setQuestion(msg.text);
        setCurrentQuestion(msg.text);
        setStatus('aria_speaking');
        setAriaSpeaking(true);
        // Audio will follow as binary
      }
      if (msg.type === 'question') {
        clearLLMTimers();
        setQuestion(msg.text);
        setCurrentQuestion(msg.text);
        setStatus('aria_speaking');
        setAriaSpeaking(true);
        // Audio will follow as binary
      }
      if (msg.type === 'transcript') {
        clearLLMTimers();
        // Add new transcript entry with real text from backend
        setTranscript(t => [...t, { q: currentQuestion, a: msg.text }]);
      }
      if (msg.type === 'verdict') {
        clearLLMTimers();
        setVerdict(msg.data || msg.text);
        setStatus('complete');
        setStep('verdict');
      }
      if (msg.type === 'error') {
        clearLLMTimers();
        setError(msg.text);
      }
    };
    socket.onerror = () => setError("WebSocket error. Please refresh.");
    socket.onclose = () => {};

    // LLM processing status timers
    llmTimeout = setTimeout(() => {
      setStatus('ARIA is thinking...');
    }, 2000);
    llmLongTimeout = setTimeout(() => {
      setStatus('Still processing, please wait...');
    }, 10000);

    return () => { socket.close(); clearLLMTimers(); };
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
    setRecording(true);
    setAudioBlob(null);
    audioChunks.current = [];
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    mediaRecorder.current = recorder;
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.current.push(e.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(audioChunks.current, { type: 'audio/webm' });
      setAudioBlob(blob);
      stream.getTracks().forEach(track => track.stop());
    };
    recorder.start();
  };
  const stopRecording = () => {
    setRecording(false);
    mediaRecorder.current?.stop();
  };

  // Send audio to backend
  const handleSubmitAnswer = () => {
    if (!wsRef.current || !audioBlob) return;
    setProcessing(true);
    setStatus("processing");
    wsRef.current.send(audioBlob);
    setAudioBlob(null);
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
  if (step === 'welcome' && applicant) {
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
            {status === 'processing' && 'Processing your answer...'}
            {status === 'ARIA is thinking...' && 'ARIA is thinking...'}
            {status === 'Still processing, please wait...' && 'Still processing, please wait...'}
            {status === 'complete' && 'Interview complete.'}
            {![
              'aria_speaking',
              'recording_ready',
              'recording',
              'processing',
              'ARIA is thinking...',
              'Still processing, please wait...',
              'complete'
            ].includes(status) && status}
          </div>
          <button
            className={recording ? styles.micBtn + ' ' + styles.micRecording : styles.micBtn + ' ' + styles.micIdle}
            onClick={recording ? stopRecording : startRecording}
            disabled={status !== 'recording_ready' || recording}
            aria-label={recording ? "Stop recording" : "Start recording"}
          >
            <span role="img" aria-label="mic">🎤</span>
          </button>
          {recording && <div className={styles.waveform}>[Waveform]</div>}
          {audioBlob && (
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
