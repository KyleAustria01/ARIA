import React from "react";
import styles from "./ARIAAvatar.module.css";

interface ARIAAvatarProps {
  isSpeaking: boolean;
  isThinking: boolean;
}

const ARIAAvatar: React.FC<ARIAAvatarProps> = ({ isSpeaking, isThinking }) => (
  <div className={styles.wrapper}>
    <div
      className={[
        styles.ring,
        isSpeaking ? styles.speaking : "",
        isThinking ? styles.thinking : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className={styles.core}>
        <span className={styles.label}>ARIA</span>
      </div>
    </div>
    <p className={styles.status}>
      {isThinking ? "Thinking…" : isSpeaking ? "Speaking…" : "Listening"}
    </p>
  </div>
);

export default ARIAAvatar;
