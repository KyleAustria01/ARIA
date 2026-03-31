import React, { useCallback, useEffect, useRef, useState } from "react";
import { TranscriptTurn } from "../hooks/useTranscript";
import styles from "./LiveTranscript.module.css";

interface LiveTranscriptProps {
  turns: TranscriptTurn[];
  candidateName?: string;
  isThinking?: boolean;
}

const fmtTime = (ts: number) => {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

const MessageBubble: React.FC<{ msg: TranscriptTurn; candidateName: string }> = ({
  msg,
  candidateName,
}) => {
  const isAria = msg.role === "aria";
  return (
    <div className={`${styles.messageRow} ${isAria ? styles.ariaRow : styles.candidateRow}`}>
      {isAria && <div className={styles.ariaAvatar}>🔵</div>}
      <div className={styles.messageContent}>
        <div className={`${styles.bubble} ${isAria ? styles.ariaBubble : styles.candidateBubble}`}>
          {msg.text}
        </div>
        <div className={styles.timestamp}>
          {isAria ? "ARIA" : candidateName} · {fmtTime(msg.timestamp)}
        </div>
      </div>
      {!isAria && <div className={styles.candidateAvatar}>👤</div>}
    </div>
  );
};

const LiveTranscript: React.FC<LiveTranscriptProps> = ({
  turns,
  candidateName = "You",
  isThinking = false,
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [showScrollTop, setShowScrollTop] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, isThinking]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setShowScrollTop(!nearBottom && turns.length > 4);
  }, [turns.length]);

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className={styles.scroll} ref={scrollRef} onScroll={handleScroll}>
      {turns.length === 0 && !isThinking && (
        <p className={styles.empty}>Transcript will appear here…</p>
      )}
      {turns.map((turn) => (
        <MessageBubble key={turn.id} msg={turn} candidateName={candidateName} />
      ))}
      {isThinking && (
        <div className={`${styles.messageRow} ${styles.ariaRow}`}>
          <div className={styles.ariaAvatar}>🔵</div>
          <div className={styles.messageContent}>
            <div className={styles.thinkingBubble}>
              <span className={styles.dot} />
              <span className={styles.dot} />
              <span className={styles.dot} />
            </div>
            <div className={styles.timestamp}>ARIA is thinking…</div>
          </div>
        </div>
      )}
      <div ref={bottomRef} />
      {showScrollTop && (
        <button type="button" className={styles.scrollBtn} onClick={scrollToBottom}>
          ↓ New messages
        </button>
      )}
    </div>
  );
};

export default LiveTranscript;
