import React from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faVideo,
  faVideoSlash,
  faSpinner,
  faBan,
} from "@fortawesome/free-solid-svg-icons";
import type { CameraStatus } from "../hooks/useCamera";
import styles from "./VideoTile.module.css";

interface VideoTileProps {
  /** Attach to the <video> element for the local camera feed. */
  videoRef?: React.Ref<HTMLVideoElement>;
  /** Display name shown in the bottom-left label. */
  label: string;
  /** Camera lifecycle status — drives which overlay to show. */
  cameraStatus?: CameraStatus;
  /** True when the camera feed is live (shorthand for status === "active"). */
  isEnabled?: boolean;
  /** Optional node rendered when the camera is off (e.g. ARIALogo orb). */
  placeholder?: React.ReactNode;
  /** Called when the user clicks the camera toggle button. */
  onToggleCamera?: () => void;
  /** Called when the user clicks "Enable Camera" after denial. */
  onRetryCamera?: () => void;
  /** If true, this tile is the ARIA AI tile (no camera controls). */
  isAria?: boolean;
}

const VideoTile: React.FC<VideoTileProps> = ({
  videoRef,
  label,
  cameraStatus = "off",
  isEnabled = false,
  placeholder,
  onToggleCamera,
  onRetryCamera,
  isAria = false,
}) => {
  const initials = label
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className={styles.tile}>
      {/* ── Camera feed ─────────────────────────────── */}
      {isEnabled && videoRef ? (
        <video
          ref={videoRef}
          className={styles.video}
          autoPlay
          muted
          playsInline
        />
      ) : (
        <div className={styles.placeholder}>
          {/* Loading spinner */}
          {cameraStatus === "loading" && (
            <div className={styles.spinnerWrap}>
              <FontAwesomeIcon icon={faSpinner} spin className={styles.spinnerIcon} />
              <span className={styles.spinnerText}>Starting camera…</span>
            </div>
          )}

          {/* Permission denied */}
          {cameraStatus === "denied" && (
            <div className={styles.deniedWrap}>
              <FontAwesomeIcon icon={faBan} className={styles.deniedIcon} />
              <span className={styles.deniedText}>Camera access denied</span>
              {onRetryCamera && (
                <button
                  type="button"
                  className={styles.enableBtn}
                  onClick={onRetryCamera}
                >
                  Enable Camera
                </button>
              )}
            </div>
          )}

          {/* Camera off — show placeholder or avatar initials */}
          {(cameraStatus === "off" || (!isEnabled && cameraStatus === "active")) && (
            placeholder ?? (
              <span className={styles.initials}>{initials || "?"}</span>
            )
          )}
        </div>
      )}

      {/* ── Bottom-left label ───────────────────────── */}
      <span className={styles.label}>{label}</span>

      {/* ── Bottom-right camera toggle (user tile only) ── */}
      {!isAria && onToggleCamera && (
        <button
          type="button"
          className={`${styles.camToggle} ${isEnabled ? styles.camOn : styles.camOff}`}
          onClick={onToggleCamera}
          aria-label={isEnabled ? "Turn camera off" : "Turn camera on"}
        >
          <FontAwesomeIcon icon={isEnabled ? faVideo : faVideoSlash} />
        </button>
      )}
    </div>
  );
};

export default VideoTile;
