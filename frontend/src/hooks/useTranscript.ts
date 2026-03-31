import { useCallback, useState } from "react";

export interface TranscriptTurn {
  id: string;
  role: "aria" | "applicant";
  text: string;
  timestamp: number;
}

interface UseTranscriptReturn {
  turns: TranscriptTurn[];
  addTurn: (role: "aria" | "applicant", text: string) => void;
  clear: () => void;
}

export function useTranscript(): UseTranscriptReturn {
  const [turns, setTurns] = useState<TranscriptTurn[]>([]);

  const addTurn = useCallback((role: "aria" | "applicant", text: string) => {
    setTurns((prev) => [
      ...prev,
      { id: `${Date.now()}-${Math.random()}`, role, text, timestamp: Date.now() },
    ]);
  }, []);

  const clear = useCallback(() => setTurns([]), []);

  return { turns, addTurn, clear };
}
