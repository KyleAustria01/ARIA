import React, { useEffect, useRef } from "react";
import styles from "./WaveformVisualizer.module.css";

interface WaveformVisualizerProps {
  isActive: boolean;
  barCount?: number;
}

const WaveformVisualizer: React.FC<WaveformVisualizerProps> = ({ isActive, barCount = 20 }) => {
  const barsRef = useRef<HTMLDivElement[]>([]);

  useEffect(() => {
    if (!isActive) {
      barsRef.current.forEach((bar) => {
        if (bar) bar.style.height = "4px";
      });
      return;
    }

    let animId: number;
    const animate = () => {
      barsRef.current.forEach((bar) => {
        if (bar) {
          const h = 4 + Math.random() * 28;
          bar.style.height = `${h}px`;
        }
      });
      animId = requestAnimationFrame(animate);
    };
    animId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animId);
  }, [isActive]);

  return (
    <div className={styles.container}>
      {Array.from({ length: barCount }).map((_, i) => (
        <div
          key={i}
          className={styles.bar}
          ref={(el) => {
            if (el) barsRef.current[i] = el;
          }}
        />
      ))}
    </div>
  );
};

export default WaveformVisualizer;
