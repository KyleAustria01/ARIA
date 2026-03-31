import React from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faVideo,
  faVideoSlash,
  faMicrophone,
  faMicrophoneSlash,
  faStop,
  faLock,
  faEllipsis,
} from "@fortawesome/free-solid-svg-icons";
import styles from "./MeetControls.module.css";

interface MeetControlsProps {
  isMicOn: boolean;
  isCamOn: boolean;
  isRecording: boolean;
  isMicDisabled?: boolean;
  micDisabledReason?: string;
  micPulse?: boolean;
  /** 0-1 live mic level from AnalyserNode. */
  audioLevel?: number;
  onToggleMic: () => void;
  onToggleCam: () => void;
  onHangUp: () => void;
}

const MeetControls: React.FC<MeetControlsProps> = ({
  isMicOn,
  isCamOn,
  isRecording,
  isMicDisabled = false,
  micDisabledReason,
  micPulse = false,
  audioLevel = 0,
  onToggleMic,
  onToggleCam,
}) => (
  <div className={styles.bar}>
    {/* Mic toggle */}
    <div className={styles.micWrap}>
      <button
        className={`${styles.btn} ${styles.micBtn} ${isRecording ? styles.recording : isMicOn ? styles.active : styles.inactive} ${isMicDisabled ? styles.disabled : ""} ${micPulse ? styles.pulse : ""}`}
        onClick={onToggleMic}
        disabled={isMicDisabled}
        title={isMicDisabled ? (micDisabledReason ?? "Mic unavailable") : isRecording ? "Stop recording" : "Record answer"}
        type="button"
        aria-label={isMicDisabled ? (micDisabledReason ?? "Mic unavailable") : isRecording ? "Stop recording" : "Record answer"}
      >
        {isMicDisabled ? (
          <FontAwesomeIcon icon={faLock} className={styles.icon} />
        ) : (
          <FontAwesomeIcon icon={isRecording ? faStop : isMicOn ? faMicrophone : faMicrophoneSlash} className={styles.icon} />
        )}
        <span className={styles.btnLabel}>{isMicDisabled ? "Locked" : isRecording ? "Stop" : "Mic"}</span>
      </button>
      {isMicDisabled && micDisabledReason && (
        <span className={styles.micHint}>{micDisabledReason}</span>
      )}
      {/* Audio level bar */}
      {isRecording && (
        <div className={styles.levelTrack}>
          <div
            className={styles.levelFill}
            style={{ width: `${Math.min(audioLevel * 100, 100)}%` }}
          />
        </div>
      )}
    </div>

    {/* Camera toggle */}
    <button
      className={`${styles.btn} ${isCamOn ? styles.active : styles.inactive}`}
      onClick={onToggleCam}
      title={isCamOn ? "Turn off camera" : "Turn on camera"}
      type="button"
      aria-label={isCamOn ? "Turn off camera" : "Turn on camera"}
    >
      <FontAwesomeIcon icon={isCamOn ? faVideo : faVideoSlash} className={styles.icon} />
      <span className={styles.btnLabel}>Camera</span>
    </button>

    {/* More (placeholder) */}
    <button
      className={`${styles.btn} ${styles.inactive}`}
      title="More options"
      type="button"
      aria-label="More options"
    >
      <FontAwesomeIcon icon={faEllipsis} className={styles.icon} />
      <span className={styles.btnLabel}>More</span>
    </button>
  </div>
);

export default MeetControls;
