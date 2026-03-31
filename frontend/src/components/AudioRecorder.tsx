import React from "react";
import { useAudio } from "../hooks/useAudio";

const AudioRecorder: React.FC<{ onAudioReady?: (blob: Blob) => void }> = ({ onAudioReady }) => {
  const { start, stop, reset, recording, audioUrl, audioBlob } = useAudio();

  const handleStop = () => {
    stop();
    if (audioBlob && onAudioReady) {
      onAudioReady(audioBlob);
    }
  };

  return (
    <div>
      <button onClick={recording ? handleStop : start}>
        {recording ? "Stop Recording" : "Start Recording"}
      </button>
      {audioUrl && (
        <div>
          <audio src={audioUrl} controls />
          <button onClick={reset}>Reset</button>
        </div>
      )}
    </div>
  );
};

export default AudioRecorder;
