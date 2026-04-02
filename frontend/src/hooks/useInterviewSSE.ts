import { useCallback, useRef, useState } from "react";

export type InterviewPhase = "idle" | "starting" | "transcribing" | "thinking" | "synthesizing" | "ready" | "closing" | "complete" | "error";

export interface SSEEvent {
  type: string;
  data: Record<string, unknown>;
}

interface UseInterviewSSEOptions {
  sessionId: string;
  onTranscription?: (text: string) => void;
  onResponse?: (text: string, data: Record<string, unknown>) => void;
  onAudio?: (audioBase64: string, format: string) => void;
  onPhaseChange?: (phase: InterviewPhase, message?: string) => void;
  onVerdict?: (verdict: Record<string, unknown>) => void;
  onError?: (message: string) => void;
  onDone?: (data: Record<string, unknown>) => void;
}

const API_BASE = import.meta.env.VITE_API_URL
  ? String(import.meta.env.VITE_API_URL).replace(/\/$/, "")
  : "";

export function useInterviewSSE(options: UseInterviewSSEOptions) {
  const {
    sessionId,
    onTranscription,
    onResponse,
    onAudio,
    onPhaseChange,
    onVerdict,
    onError,
    onDone,
  } = options;

  const [phase, setPhase] = useState<InterviewPhase>("idle");
  const [isProcessing, setIsProcessing] = useState(false);
  const [questionCount, setQuestionCount] = useState(0);
  const [maxQuestions, setMaxQuestions] = useState(12);
  const abortControllerRef = useRef<AbortController | null>(null);

  const updatePhase = useCallback((newPhase: InterviewPhase, message?: string) => {
    setPhase(newPhase);
    onPhaseChange?.(newPhase, message);
  }, [onPhaseChange]);

  const handleSSEStream = useCallback(async (response: Response) => {
    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("No response body");
    }

    const decoder = new TextDecoder();
    let buffer = "";
    // Persist event state across read chunks
    let currentEventType = "";
    let currentEventData = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            // Append data (SSE can have multiple data lines)
            currentEventData += (currentEventData ? "\n" : "") + line.slice(6);
          } else if (line === "" && currentEventType && currentEventData) {
            // Empty line signals end of event - process it
            try {
              const data = JSON.parse(currentEventData) as Record<string, unknown>;
              
              switch (currentEventType) {
                case "phase":
                  console.log("[SSE] Phase:", data.phase, data.message);
                  updatePhase(data.phase as InterviewPhase, data.message as string);
                  break;
                case "transcription":
                  console.log("[SSE] Transcription:", data.text);
                  onTranscription?.(data.text as string);
                  break;
                case "response":
                  console.log("[SSE] Response:", (data.text as string)?.slice(0, 100));
                  onResponse?.(data.text as string, data);
                  break;
                case "audio":
                  console.log("[SSE] Audio received, format:", data.format, "length:", (data.data as string)?.length);
                  onAudio?.(data.data as string, data.format as string);
                  break;
                case "verdict":
                  onVerdict?.(data);
                  break;
                case "error":
                  updatePhase("error", data.message as string);
                  onError?.(data.message as string);
                  break;
                case "done":
                  setIsProcessing(false);
                  if (data.question_count !== undefined) {
                    setQuestionCount(data.question_count as number);
                  }
                  if (data.max_questions !== undefined) {
                    setMaxQuestions(data.max_questions as number);
                  }
                  if (data.complete) {
                    updatePhase("complete");
                  } else {
                    updatePhase("ready");
                  }
                  onDone?.(data);
                  break;
              }
            } catch (e) {
              console.warn("[SSE] Failed to parse event data:", currentEventData.slice(0, 100), e);
            }
            // Reset for next event
            currentEventType = "";
            currentEventData = "";
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }, [updatePhase, onTranscription, onResponse, onAudio, onVerdict, onError, onDone]);

  const startInterview = useCallback(async () => {
    if (isProcessing) return;
    
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    
    setIsProcessing(true);
    updatePhase("starting");

    try {
      const response = await fetch(`${API_BASE}/api/interview/${sessionId}/start`, {
        method: "POST",
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`Start failed: ${response.status}`);
      }

      await handleSSEStream(response);
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      const message = (e as Error).message || "Failed to start interview";
      updatePhase("error", message);
      onError?.(message);
      setIsProcessing(false);
    }
  }, [sessionId, isProcessing, handleSSEStream, updatePhase, onError]);

  const sendTurn = useCallback(async (audioBlob?: Blob, text?: string) => {
    if (isProcessing) return;
    
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    
    setIsProcessing(true);
    updatePhase("transcribing");

    try {
      const formData = new FormData();
      if (audioBlob) {
        formData.append("audio", audioBlob, "recording.webm");
      }
      if (text) {
        formData.append("text", text);
      }

      const response = await fetch(`${API_BASE}/api/interview/${sessionId}/turn`, {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`Turn failed: ${response.status}`);
      }

      await handleSSEStream(response);
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      const message = (e as Error).message || "Failed to process turn";
      updatePhase("error", message);
      onError?.(message);
      setIsProcessing(false);
    }
  }, [sessionId, isProcessing, handleSSEStream, updatePhase, onError]);

  const sendText = useCallback(async (text: string) => {
    return sendTurn(undefined, text);
  }, [sendTurn]);

  const abort = useCallback(() => {
    abortControllerRef.current?.abort();
    setIsProcessing(false);
    updatePhase("ready");
  }, [updatePhase]);

  return {
    phase,
    isProcessing,
    questionCount,
    maxQuestions,
    startInterview,
    sendTurn,
    sendText,
    abort,
  };
}
