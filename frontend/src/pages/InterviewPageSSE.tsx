/**
 * ARIA Interview Page — SSE-based (no WebSocket)
 * 
 * Flow:
 * 1. Load session info from /api/applicant/session/{id}
 * 2. Join → POST /api/interview/{id}/start → SSE stream greeting
 * 3. User records audio → POST /api/interview/{id}/turn → SSE stream response
 * 4. Repeat until complete
 */

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
import { useInterviewSSE, InterviewPhase } from "../hooks/useInterviewSSE";
import styles from "./InterviewPage.module.css";

type PagePhase = "loading" | "prejoin" | "interview" | "done" | "error";

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

const InterviewPageSSE: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const { theme, toggle: toggleTheme } = useTheme();
  
  const [pagePhase, setPagePhase] = useState<PagePhase>("loading");
  const [info, setInfo] = useState<PreJoinInfo | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [micOn, setMicOn] = useState(true);
  
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Camera & Audio hooks
  const { videoRef, status: camStatus, isEnabled: isCamOn, toggleCamera, startCamera } = useCamera();
  const { isRecording, isPlaying, audioLevel, startRecording, stopRecording, playAudio, stopAll: stopAllAudio } = useAudio();
  const { turns, addTurn, clear: clearTranscript } = useTranscript();

  // SSE Interview hook
  const {
    phase: interviewPhase,
    isProcessing,
    questionCount,
    maxQuestions,
    startInterview,
    sendTurn,
    abort,
  } = useInterviewSSE({
    sessionId: sessionId || "",
    onTranscription: (text) => {
      addTurn("applicant", text);
    },
    onResponse: (text, data) => {
      setCurrentQuestion(text);
      addTurn("aria", text);
      setIsSpeaking(false);
    },
    onAudio: async (audioBase64, format) => {
      setIsSpeaking(true);
      try {
        // Decode base64 to ArrayBuffer
        const binary = atob(audioBase64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
          bytes[i] = binary.charCodeAt(i);
        }
        await playAudio(bytes.buffer);
      } catch (err) {
        console.error("Audio playback failed:", err);
      } finally {
        setIsSpeaking(false);
      }
    },
    onPhaseChange: (phase, message) => {
      if (message) setStatusMessage(message);
      if (phase === "complete") {
        setPagePhase("done");
      }
    },
    onVerdict: (verdict) => {
      console.log("Interview verdict:", verdict);
      setPagePhase("done");
    },
    onError: (message) => {
      setPageError(message);
      setPagePhase("error");
    },
    onDone: (data) => {
      if (data.complete) {
        setPagePhase("done");
      }
    },
  });

  // ── Elapsed timer ────────────────────────────────────────
  useEffect(() => {
    if (pagePhase === "interview" && !timerRef.current) {
      timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
    }
    return () => {
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    };
  }, [pagePhase]);

  const fmtTime = (s: number) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    const mm = String(m).padStart(2, "0");
    const ss = String(sec).padStart(2, "0");
    return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
  };

  // ── 1. Load pre-join info ────────────────────────────────
  useEffect(() => {
    if (!sessionId) { setPageError("No session ID"); setPagePhase("error"); return; }
    fetch(`/api/applicant/session/${sessionId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Session not found (${r.status})`);
        return r.json();
      })
      .then((data: PreJoinInfo) => {
        if (data.is_complete) { setPagePhase("done"); return; }
        setInfo(data);
        // Restore conversation history if resuming
        if (data.is_resuming && data.conversation_history?.length > 0) {
          data.conversation_history.forEach((turn) => {
            addTurn(turn.role, turn.text);
          });
          const lastAria = [...data.conversation_history].reverse().find((t) => t.role === "aria");
          if (lastAria) {
            setCurrentQuestion(lastAria.text);
          }
        }
        setPagePhase("prejoin");
      })
      .catch((err: Error) => { setPageError(err.message); setPagePhase("error"); });
  }, [sessionId, addTurn]);

  // ── 2. Join and start interview ──────────────────────────
  const handleJoin = async () => {
    if (!sessionId) return;
    try {
      await fetch(`/api/applicant/join/${sessionId}`, { method: "POST" });
    } catch {
      // non-critical
    }
    setPagePhase("interview");
    // Start the interview — this sends greeting
    startInterview();
  };

  // ── 3. Recording controls ────────────────────────────────
  const ariaOccupied = isSpeaking || isProcessing || isPlaying;

  const handleToggleMic = useCallback(async () => {
    if (isRecording) {
      // Stop recording and send the audio
      const audioBlob = await stopRecording();
      if (audioBlob && audioBlob.size > 0) {
        sendTurn(audioBlob);
      }
      return;
    }
    
    if (ariaOccupied) return;
    
    if (micOn) {
      // Start recording
      startRecording();
    } else {
      setMicOn((v) => !v);
    }
  }, [isRecording, micOn, ariaOccupied, stopRecording, startRecording, sendTurn]);

  const handleHangUp = useCallback(() => {
    stopAllAudio();
    abort();
    window.close();
    setPagePhase("done");
  }, [stopAllAudio, abort]);

  // ── Determine status for UI ──────────────────────────────
  const getInterviewStatus = (): string => {
    if (isRecording) return "recording";
    if (isSpeaking || isPlaying) return "aria_speaking";
    if (isProcessing) return "processing";
    return "recording_ready";
  };
  const interviewStatus = getInterviewStatus();

  // ── Render states ────────────────────────────────────────

  if (pagePhase === "loading") {
    return (
      <div className={styles.center}>
        <div className={styles.spinner} />
        <span>Loading session…</span>
      </div>
    );
  }

  if (pagePhase === "error") {
    return (
      <div className={styles.center}>
        <p className={styles.error}>{pageError}</p>
      </div>
    );
  }

  if (pagePhase === "done") {
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
  if (pagePhase === "prejoin" && info) {
    return (
      <div className={styles.prejoin}>
        <div className={styles.prejoinCard}>
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

          {info.is_resuming && (
            <div className={styles.resumeNotice}>
              <FontAwesomeIcon icon={faCircleInfo} className={styles.tipIcon} />
              <span>Your previous progress has been saved. Click below to continue where you left off.</span>
            </div>
          )}

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
          <span className={`${styles.wsBadge} ${styles.wsBadgeOn}`}>
            ● {questionCount}/{maxQuestions}
          </span>
        </div>
      </header>

      {/* ── Stage: video left (60%) + right panel (40%) ─── */}
      <div className={styles.stage}>
        {/* ── Left: Video Area ─────────────────────────────── */}
        <div className={styles.videoArea}>
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

          <div className={styles.ariaRow}>
            <div className={styles.ariaOrbWrap}>
              <ARIAAvatar isSpeaking={isSpeaking} isThinking={isProcessing} />
            </div>
            <div className={styles.ariaStatus}>
              {isSpeaking && <span className={styles.statusLabel}>ARIA is speaking…</span>}
              {isProcessing && !isSpeaking && (
                <span className={styles.statusLabel}>
                  <span className={styles.thinkDot} /> {statusMessage || "ARIA is thinking…"}
                </span>
              )}
              {!isSpeaking && !isProcessing && !isRecording && (
                <span className={styles.statusReady}>Your turn to answer</span>
              )}
              {isRecording && (
                <span className={`${styles.statusLabel} ${styles.statusRec}`}>
                  <span className={styles.recDot} /> Recording…
                </span>
              )}
            </div>
          </div>

          <div className={styles.waveStrip}>
            <WaveformVisualizer isActive={isRecording || isSpeaking} />
          </div>

          <MeetControls
            isMicOn={micOn}
            isCamOn={isCamOn}
            isRecording={isRecording}
            isMicDisabled={ariaOccupied}
            micPulse={false}
            audioLevel={audioLevel}
            micDisabledReason={
              isSpeaking || isPlaying
                ? "ARIA is speaking…"
                : isProcessing
                  ? statusMessage || "Processing…"
                  : undefined
            }
            onToggleMic={handleToggleMic}
            onToggleCam={toggleCamera}
            onHangUp={handleHangUp}
          />
        </div>

        {/* ── Right Panel ──────────────────────────────────── */}
        <aside className={styles.rightPanel}>
          {currentQuestion && (
            <div className={styles.questionCard}>
              <div className={styles.questionHeader}>
                <span className={styles.questionBadge}>Q{questionCount || 1}</span>
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
              isThinking={isProcessing}
            />
          </div>
        </aside>
      </div>
    </div>
  );
};

export default InterviewPageSSE;
