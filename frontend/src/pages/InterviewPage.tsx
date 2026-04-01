import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faVideo,
  faMicrophone,
  faCheck,
  faCircleInfo,
  faShieldHalved,
  faArrowLeft,
  faClock,
  faStop,
  faMoon,
  faSun,
} from "@fortawesome/free-solid-svg-icons";
import ARIAAvatar from "../components/ARIAAvatar";
import LiveTranscript from "../components/LiveTranscript";
import MeetControls from "../components/MeetControls";
import VideoTile from "../components/VideoTile";
import WaveformVisualizer from "../components/WaveformVisualizer";
import { useAudio } from "../hooks/useAudio";
import { useCamera } from "../hooks/useCamera";
import { useTheme } from "../hooks/useTheme";
import { useTranscript } from "../hooks/useTranscript";
import { useWebSocket } from "../hooks/useWebSocket";
import styles from "./InterviewPage.module.css";

type Phase = "loading" | "prejoin" | "interview" | "done" | "error";

interface ConversationTurn {
  role: "aria" | "applicant";
  text: string;
}

interface PreJoinInfo {
  candidate_name: string;
  job_title: string;
  company: string;
  max_questions: number;
  is_complete: boolean;
  is_resuming: boolean;
  question_count: number;
  conversation_history: ConversationTurn[];
}

// WebSocket base: use VITE_WS_URL env var in production (Render backend),
// fall back to same-host for local dev (Vite proxy handles /ws/* → backend).
const WS_BASE: string = import.meta.env.VITE_WS_URL
  ? String(import.meta.env.VITE_WS_URL).replace(/\/$/, "")
  : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;

const InterviewPage: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const { theme, toggle: toggleTheme } = useTheme();
  const [phase, setPhase] = useState<Phase>("loading");
  const [info, setInfo] = useState<PreJoinInfo | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [questionCount, setQuestionCount] = useState(0);
  const [currentQuestion, setCurrentQuestion] = useState<string | null>(null);
  const [wsEnabled, setWsEnabled] = useState(false);
  const [micPulse, setMicPulse] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [showDebug, setShowDebug] = useState(false);
  const [debugLog, setDebugLog] = useState<Record<string, unknown>[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { videoRef, status: camStatus, isEnabled: isCamOn, toggleCamera, startCamera } = useCamera();
  const { isRecording, isPlaying, audioLevel, startRecording, stopRecording, playAudio, stopAll: stopAllAudio } = useAudio();
  const { turns, addTurn, clear: clearTranscript } = useTranscript();
  const verdictRef = useRef<Record<string, unknown> | null>(null);
  const sendJsonRef = useRef<(payload: object) => void>(() => {});

  // ── Debug panel toggle (Ctrl+D) ──────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === "d") {
        e.preventDefault();
        setShowDebug((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // ── Elapsed timer ────────────────────────────────────────────────────────
  useEffect(() => {
    if (phase === "interview" && !timerRef.current) {
      timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
    }
    return () => {
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    };
  }, [phase]);

  const fmtTime = (s: number) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    const mm = String(m).padStart(2, "0");
    const ss = String(sec).padStart(2, "0");
    return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
  };

  const interviewStatus: string = isRecording
    ? "recording"
    : isSpeaking || isPlaying
      ? "aria_speaking"
      : isThinking
        ? "processing"
        : "recording_ready";

  // ── 1. Load pre-join info ────────────────────────────────────────────────
  useEffect(() => {
    if (!sessionId) { setPageError("No session ID"); setPhase("error"); return; }
    fetch(`/api/applicant/session/${sessionId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Session not found (${r.status})`);
        return r.json();
      })
      .then((data: PreJoinInfo) => {
        if (data.is_complete) { setPhase("done"); return; }
        setInfo(data);
        setPhase("prejoin");
      })
      .catch((err: Error) => { setPageError(err.message); setPhase("error"); });
  }, [sessionId]);

  // ── 2. WebSocket message handler ─────────────────────────────────────────
  const handleJsonMessage = useCallback(
    (msg: Record<string, unknown>) => {
      const type = msg.type as string;

      if (type === "resume") {
        // Restore conversation history from server
        const history = msg.conversation_history as ConversationTurn[];
        const qCount = msg.question_count as number;
        setQuestionCount(qCount || 0);
        // Clear existing transcript to prevent duplicates
        clearTranscript();
        if (history && history.length > 0) {
          history.forEach((turn) => {
            addTurn(turn.role, turn.text);
          });
          // Set the last ARIA question as current
          const lastAria = [...history].reverse().find((t) => t.role === "aria");
          if (lastAria) {
            setCurrentQuestion(lastAria.text);
          }
        }
        setStatusMessage("Resuming interview...");
      } else if (type === "transcript") {
        const role = msg.role as "aria" | "applicant";
        const text = msg.text as string;
        if (role === "aria") {
          setQuestionCount((msg.question_count as number) || 0);
          setCurrentQuestion(text);
          setIsThinking(false);
          setIsSpeaking(false);
          addTurn("aria", text);
        } else {
          addTurn("applicant", text);
        }
      } else if (type === "thinking") {
        setIsThinking(true);
        setIsSpeaking(false);
      } else if (type === "verdict") {
        verdictRef.current = msg.data as Record<string, unknown>;
        setPhase("done");
      } else if (type === "error") {
        setPageError(msg.message as string);
        setPhase("error");
      } else if (type === "checkin") {
        setStatusMessage(msg.text as string);
        addTurn("aria", msg.text as string);
        setMicPulse(true);
        setTimeout(() => setMicPulse(false), 3000);
      } else if (type === "timeout") {
        setPageError(msg.text as string);
        setPhase("error");
      } else if (type === "debug") {
        setDebugLog((prev) => [...prev.slice(-19), msg]);
      } else if (type === "resumed") {
        setStatusMessage(msg.text as string);
      } else if (type === "retry") {
        setStatusMessage(msg.text as string || "Please try again.");
      }
    },
    [addTurn, clearTranscript, sessionId]
  );

  const handleBinaryMessage = useCallback(
    async (buffer: ArrayBuffer) => {
      console.log("[ARIA audio] received binary frame:", buffer.byteLength, "bytes");
      if (buffer.byteLength === 0) {
        console.warn("[ARIA audio] empty audio buffer — TTS may have failed on backend");
        return;
      }
      setIsSpeaking(true);
      setIsThinking(false);
      try {
        await playAudio(buffer);
        console.log("[ARIA audio] playback finished");
      } catch (err) {
        console.error("[ARIA audio] playback error:", err);
      } finally {
        setIsSpeaking(false);
        // Tell backend audio playback finished — resets idle timer
        sendJsonRef.current({ type: "ready" });
      }
    },
    [playAudio]
  );

  const { status: wsStatus, sendJson, sendBinary, close: closeWs } = useWebSocket({
    url: `${WS_BASE}/ws/interview/${sessionId}`,
    onJsonMessage: handleJsonMessage,
    onBinaryMessage: handleBinaryMessage,
    enabled: wsEnabled,
  });

  // Keep ref in sync so handleBinaryMessage can send "ready" signal
  sendJsonRef.current = sendJson;

  // ── 3. Join ──────────────────────────────────────────────────────────────
  const handleJoin = async () => {
    if (!sessionId) return;
    try {
      await fetch(`/api/applicant/join/${sessionId}`, { method: "POST" });
    } catch {
      // non-critical
    }
    setPhase("interview");
    setWsEnabled(true);
  };

  // ── 4. Recording controls ────────────────────────────────────────────────
  const [micOn, setMicOn] = useState(true);

  // ── Safety watchdog: force-reset stuck speaking/thinking state after 30 s ──
  useEffect(() => {
    if (!isSpeaking && !isThinking) return;
    const timer = setTimeout(() => {
      console.warn("[ARIA] Speaking/thinking state stuck — force resetting");
      setIsSpeaking(false);
      setIsThinking(false);
    }, 30_000);
    return () => clearTimeout(timer);
  }, [isSpeaking, isThinking]);

  const ariaOccupied = isSpeaking || isThinking || isPlaying;

  const handleToggleMic = useCallback(() => {
    if (isRecording) {
      sendJson({ type: "recording_stopped" });
      stopRecording();
      setMicOn(true);
      return;
    }
    if (ariaOccupied) return;
    if (micOn && wsStatus === "open") {
      sendJson({ type: "recording_started" });
      startRecording((buffer) => sendBinary(buffer));
    } else {
      setMicOn((v) => !v);
    }
  }, [isRecording, micOn, ariaOccupied, wsStatus, stopRecording, startRecording, sendBinary, sendJson]);

  const handleHangUp = useCallback(() => {
    stopAllAudio();
    closeWs();
    window.close();
    setPhase("done");
  }, [stopAllAudio, closeWs]);

  const maxQ = info?.max_questions ?? 12;

  // ── Render ────────────────────────────────────────────────────────────────

  if (phase === "loading") {
    return (
      <div className={styles.center}>
        <div className={styles.spinner} />
        <span>Loading session…</span>
      </div>
    );
  }

  if (phase === "error") {
    return (
      <div className={styles.center}>
        <p className={styles.error}>{pageError}</p>
      </div>
    );
  }

  if (phase === "done") {
    return (
      <div className={styles.center}>
        <div className={styles.doneIcon}>
          <FontAwesomeIcon icon={faCheck} />
        </div>
        <p className={styles.doneMsg}>Interview complete!</p>
        <p className={styles.doneHint}>Thank you for your time. You may close this tab.</p>
      </div>
    );
  }

  /* ── Pre-Join ──────────────────────────────────────────── */
  if (phase === "prejoin" && info) {
    return (
      <div className={styles.prejoin}>
        <div className={styles.prejoinCard}>
          {/* Logo */}
          <div className={styles.logoDots}>
            <span className={styles.dotIndigo} />
            <span className={styles.dotPurple} />
          </div>

          <h1 className={styles.prejoinTitle}>
            {info.is_resuming ? "Welcome back, " : "Welcome, "}{info.candidate_name}
          </h1>
          <p className={styles.prejoinSub}>
            {info.is_resuming ? (
              <>
                Resuming your interview for{" "}
                <strong>{info.job_title || "this position"}</strong>
                {info.company ? <> at <strong>{info.company}</strong></> : ""}
                {" "}(Question {info.question_count} of {info.max_questions})
              </>
            ) : (
              <>
                Pre-screening interview for{" "}
                <strong>{info.job_title || "this position"}</strong>
                {info.company ? <> at <strong>{info.company}</strong></> : ""}
              </>
            )}
          </p>

          {/* Resume notice */}
          {info.is_resuming && (
            <div className={styles.resumeNotice}>
              <FontAwesomeIcon icon={faCircleInfo} className={styles.tipIcon} />
              <span>Your previous progress has been saved. Click below to continue where you left off.</span>
            </div>
          )}

          {/* Camera preview */}
          <div className={styles.prejoinPreview}>
            <VideoTile
              videoRef={videoRef}
              label="You"
              cameraStatus={camStatus}
              isEnabled={isCamOn}
              onToggleCamera={toggleCamera}
              onRetryCamera={startCamera}
            />
          </div>

          {/* Tips */}
          <div className={styles.tipList}>
            <div className={styles.tipItem}>
              <FontAwesomeIcon icon={faMicrophone} className={styles.tipIcon} />
              <span>Click the mic button to record, click again to submit</span>
            </div>
            <div className={styles.tipItem}>
              <FontAwesomeIcon icon={faVideo} className={styles.tipIcon} />
              <span>Camera is optional but recommended</span>
            </div>
            {!info.is_resuming && (
              <div className={styles.tipItem}>
                <FontAwesomeIcon icon={faCircleInfo} className={styles.tipIcon} />
                <span>Up to <strong>{info.max_questions}</strong> questions will be asked</span>
              </div>
            )}
            <div className={styles.tipItem}>
              <FontAwesomeIcon icon={faShieldHalved} className={styles.tipIcon} />
              <span>Your responses are processed securely</span>
            </div>
          </div>

          <button className={styles.joinBtn} type="button" onClick={handleJoin}>
            {info.is_resuming ? "Continue Interview" : "Join Interview"}
          </button>
        </div>
      </div>
    );
  }

  /* ── Main Interview Room ───────────────────────────────── */
  return (
    <div className={styles.meetRoot}>
      {/* ── Top Bar ───────────────────────────────────────── */}
      <header className={styles.topBar}>
        <div className={styles.topBarLeft}>
          <button
            type="button"
            className={styles.topBarBackBtn}
            onClick={() => navigate("/")}
            aria-label="Back"
          >
            <FontAwesomeIcon icon={faArrowLeft} />
          </button>
          <div className={styles.logoDots}>
            <span className={styles.dotIndigo} />
            <span className={styles.dotPurple} />
          </div>
          <span className={styles.logoText}>ARIA</span>
          {info && (
            <span className={styles.topInfo}>
              Hiring: {info.job_title}{info.company ? ` · ${info.company}` : ""}
            </span>
          )}
        </div>
        <div className={styles.topBarRight}>
          <span className={styles.timer}>
            <FontAwesomeIcon icon={faClock} /> {fmtTime(elapsed)}
          </span>
          <button
            type="button"
            className={styles.themeToggle}
            onClick={toggleTheme}
            aria-label="Toggle theme"
          >
            <FontAwesomeIcon icon={theme === "dark" ? faSun : faMoon} />
          </button>
          <button
            type="button"
            className={styles.endBtn}
            onClick={handleHangUp}
          >
            <FontAwesomeIcon icon={faStop} /> End
          </button>
          <span
            className={`${styles.wsBadge} ${
              wsStatus === "open" ? styles.wsBadgeOn : ""
            }`}
          >
            {wsStatus === "open" ? "● Live" : "Connecting"}
          </span>
        </div>
      </header>

      {/* ── Stage: video left (60%) + right panel (40%) ─── */}
      <div className={styles.stage}>
        {/* ── Left: Video Area ─────────────────────────────── */}
        <div className={styles.videoArea}>
          {/* Large applicant tile */}
          <div className={styles.mainTile}>
            <VideoTile
              videoRef={videoRef}
              label={info?.candidate_name ?? "You"}
              cameraStatus={camStatus}
              isEnabled={isCamOn}
              onToggleCamera={toggleCamera}
              onRetryCamera={startCamera}
            />
          </div>

          {/* ARIA orb row */}
          <div className={styles.ariaRow}>
            <div className={styles.ariaOrbWrap}>
              <ARIAAvatar isSpeaking={isSpeaking} isThinking={isThinking} />
            </div>
            <div className={styles.ariaStatus}>
              {isSpeaking && <span className={styles.statusLabel}>ARIA is speaking…</span>}
              {isThinking && (
                <span className={styles.statusLabel}>
                  <span className={styles.thinkDot} /> ARIA is thinking…
                </span>
              )}
              {!isSpeaking && !isThinking && !isRecording && (
                <span className={styles.statusReady}>Your turn to answer</span>
              )}
              {isRecording && (
                <span className={`${styles.statusLabel} ${styles.statusRec}`}>
                  <span className={styles.recDot} /> Recording…
                </span>
              )}
            </div>
          </div>

          {/* Waveform strip */}
          <div className={styles.waveStrip}>
            <WaveformVisualizer isActive={isRecording || isSpeaking} />
          </div>

          {/* Controls */}
          <MeetControls
            isMicOn={micOn}
            isCamOn={isCamOn}
            isRecording={isRecording}
            isMicDisabled={ariaOccupied}
            micPulse={micPulse}
            audioLevel={audioLevel}
            micDisabledReason={
              isSpeaking || isPlaying
                ? "ARIA is speaking…"
                : isThinking
                  ? "ARIA is thinking…"
                  : undefined
            }
            onToggleMic={handleToggleMic}
            onToggleCam={toggleCamera}
            onHangUp={handleHangUp}
          />
        </div>

        {/* ── Right Panel ──────────────────────────────────── */}
        <aside className={styles.rightPanel}>
          {/* Current Question Card */}
          {currentQuestion && (
            <div className={styles.questionCard}>
              <div className={styles.questionHeader}>
                <span className={styles.questionBadge}>Q{questionCount}</span>
                <span className={styles.questionStatus}>
                  {interviewStatus === "aria_speaking" && "🔊 ARIA Speaking"}
                  {interviewStatus === "recording_ready" && "🎤 Your Turn"}
                  {interviewStatus === "recording" && "⏺ Recording"}
                  {interviewStatus === "processing" && "⚙️ Processing"}
                </span>
              </div>
              <p className={styles.questionText}>{currentQuestion}</p>
              {interviewStatus === "recording_ready" && (
                <div className={styles.recordingHint}>
                  Press the mic button to answer
                </div>
              )}
            </div>
          )}

          {/* Transcript */}
          <div className={styles.transcriptSection}>
            <div className={styles.sidebarHeader}>
              <h3 className={styles.sidebarTitle}>Transcript</h3>
              <span className={styles.sidebarCount}>
                {turns.length} {turns.length === 1 ? "msg" : "msgs"}
              </span>
            </div>
            <LiveTranscript
              turns={turns}
              candidateName={info?.candidate_name ?? "You"}
              isThinking={isThinking}
            />
          </div>
        </aside>
      </div>

      {/* ── Debug Panel (Ctrl+D in dev) ───────────────────── */}
      {showDebug && (
        <div className={styles.debugPanel}>
          <div className={styles.debugHeader}>
            <h4 className={styles.debugTitle}>Debug Panel</h4>
            <button type="button" className={styles.debugClose} onClick={() => setShowDebug(false)}>×</button>
          </div>
          <div className={styles.debugBody}>
            {debugLog.length === 0 ? (
              <p className={styles.debugEmpty}>No debug events yet. Waiting for node executions…</p>
            ) : (
              debugLog.map((entry, i) => (
                <details key={i} className={styles.debugEntry}>
                  <summary className={styles.debugSummary}>
                    [{(entry.node as string) || "?"}]
                  </summary>
                  <pre className={styles.debugPre}>
                    {JSON.stringify(entry.state_summary, null, 2)}
                  </pre>
                </details>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default InterviewPage;
