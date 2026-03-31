import React from "react";
import styles from "./ARIALogo.module.css";

type ARIALogoState = "idle" | "speaking" | "thinking" | "complete";

interface ARIALogoProps {
  state?: ARIALogoState;
}

const ARIALogo: React.FC<ARIALogoProps> = ({ state = "idle" }) => {
  const stateClass = styles[state] || styles.idle;

  const statusText: Record<ARIALogoState, string> = {
    idle: "Listening",
    speaking: "Speaking…",
    thinking: "Thinking…",
    complete: "Interview Complete",
  };

  return (
    <div className={styles.wrapper}>
      <div className={`${styles.orb} ${stateClass}`}>
        <svg className={styles.orbSvg} viewBox="0 0 140 140">
          <defs>
            <radialGradient id="coreGrad" cx="50%" cy="45%" r="50%">
              <stop offset="0%" stopColor="#312e81" />
              <stop offset="100%" stopColor="#1e1b4b" />
            </radialGradient>
          </defs>

          {/* Floating particles */}
          <circle className={styles.particle} cx="20" cy="25" r="2" />
          <circle className={styles.particle} cx="118" cy="35" r="1.8" />
          <circle className={styles.particle} cx="30" cy="110" r="1.5" />
          <circle className={styles.particle} cx="112" cy="105" r="2.2" />
          <circle className={styles.particle} cx="70" cy="12" r="1.6" />
          <circle className={styles.particle} cx="70" cy="128" r="1.4" />

          {/* Outer ring */}
          <circle className={styles.ring} cx="70" cy="70" r="60" />

          {/* Core orb */}
          <circle
            className={styles.core}
            cx="70"
            cy="70"
            r="45"
            fill="url(#coreGrad)"
          />

          {/* Waveform bars (speaking state) */}
          <g className={styles.waveGroup}>
            <rect className={styles.waveBar} x="52" y="62" width="3" height="16" />
            <rect className={styles.waveBar} x="59" y="58" width="3" height="24" />
            <rect className={styles.waveBar} x="66" y="55" width="3" height="30" />
            <rect className={styles.waveBar} x="73" y="58" width="3" height="24" />
            <rect className={styles.waveBar} x="80" y="62" width="3" height="16" />
          </g>

          {/* Thinking orbit dots */}
          <g className={styles.thinkGroup}>
            <circle className={styles.thinkDot} cx="70" cy="18" r="3" />
            <circle className={styles.thinkDot} cx="115" cy="88" r="2.5" />
            <circle className={styles.thinkDot} cx="25" cy="88" r="2" />
          </g>

          {/* Complete checkmark */}
          <g className={styles.checkGroup}>
            <path
              className={styles.checkPath}
              d="M55 70 L65 80 L85 58"
            />
          </g>

          {/* ARIA label (hidden during complete — checkmark takes over) */}
          {state !== "complete" && (
            <text className={styles.label} x="70" y="71">
              ARIA
            </text>
          )}
        </svg>
      </div>
      <p className={styles.status}>{statusText[state]}</p>
    </div>
  );
};

export default ARIALogo;
