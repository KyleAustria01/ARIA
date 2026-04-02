import { useCallback, useRef, useState } from "react";

const CHUNK_SIZE = 1024 * 1024; // 1 MB
const POLL_INTERVAL_MS = 1500;

// Use VITE_API_URL in production (points to Render backend)
const API_ROOT = import.meta.env.VITE_API_URL
  ? String(import.meta.env.VITE_API_URL).replace(/\/$/, "")
  : "";
const API_BASE = `${API_ROOT}/api/recruiter`;

export type UploadType = "jd" | "resume";

export type UploadStatus =
  | "idle"
  | "uploading"
  | "assembling"
  | "analyzing"
  | "complete"
  | "error";

export interface ChunkedUploadResult {
  upload_id: string;
  session_id: string;
  result: Record<string, unknown>;
}

export interface UseChunkedUpload {
  upload: (
    file: File,
    uploadType: UploadType,
    sessionId?: string,
  ) => Promise<ChunkedUploadResult>;
  progress: number;
  status: UploadStatus;
  result: Record<string, unknown> | null;
  error: string | null;
  cancel: () => void;
}

/**
 * React hook for chunked PDF uploads with background processing.
 *
 * Flow:
 *  1. POST /upload/init        → get upload_id + session_id
 *  2. POST /upload/chunk  (×N) → send 1 MB chunks sequentially
 *  3. GET  /upload/status/{id} → poll until complete / error
 */
export const useChunkedUpload = (): UseChunkedUpload => {
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cancelledRef = useRef(false);

  const cancel = useCallback(() => {
    cancelledRef.current = true;
  }, []);

  const upload = useCallback(
    async (
      file: File,
      uploadType: UploadType,
      sessionId?: string,
    ): Promise<ChunkedUploadResult> => {
      cancelledRef.current = false;
      setStatus("uploading");
      setProgress(0);
      setError(null);
      setResult(null);

      const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

      // ── Step 1: Initialise upload session ─────────────────────────
      const initForm = new FormData();
      initForm.append("file_name", file.name);
      initForm.append("file_size", String(file.size));
      initForm.append("total_chunks", String(totalChunks));
      initForm.append("upload_type", uploadType);
      if (sessionId) initForm.append("session_id", sessionId);

      const initRes = await fetch(`${API_BASE}/upload/init`, {
        method: "POST",
        body: initForm,
      });
      if (!initRes.ok) {
        const msg = await initRes.text();
        setStatus("error");
        setError(msg);
        throw new Error(msg);
      }
      const { upload_id, session_id: newSessionId } = await initRes.json();

      // ── Step 2: Upload chunks sequentially ────────────────────────
      for (let i = 0; i < totalChunks; i++) {
        if (cancelledRef.current) {
          setStatus("idle");
          throw new Error("Upload cancelled");
        }

        const start = i * CHUNK_SIZE;
        const end = Math.min(start + CHUNK_SIZE, file.size);
        const blob = file.slice(start, end);

        const chunkForm = new FormData();
        chunkForm.append("upload_id", upload_id);
        chunkForm.append("chunk_index", String(i));
        chunkForm.append("total_chunks", String(totalChunks));
        chunkForm.append("chunk", blob, file.name);

        const chunkRes = await fetch(`${API_BASE}/upload/chunk`, {
          method: "POST",
          body: chunkForm,
        });
        if (!chunkRes.ok) {
          const msg = await chunkRes.text();
          setStatus("error");
          setError(msg);
          throw new Error(msg);
        }

        setProgress(Math.round(((i + 1) / totalChunks) * 100));
      }

      // ── Step 3: Poll for processing result ────────────────────────
      setStatus("assembling");
      const pollResult = await pollStatus(upload_id);
      setResult(pollResult);
      setStatus("complete");

      return {
        upload_id,
        session_id: newSessionId,
        result: pollResult,
      };
    },
    [],
  );

  /** Poll GET /upload/status/{id} until complete or error. */
  async function pollStatus(
    uploadId: string,
  ): Promise<Record<string, unknown>> {
    for (;;) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));

      if (cancelledRef.current) {
        setStatus("idle");
        throw new Error("Upload cancelled");
      }

      const res = await fetch(`${API_BASE}/upload/status/${uploadId}`);
      if (!res.ok) {
        setStatus("error");
        setError("Failed to fetch upload status");
        throw new Error("Failed to fetch upload status");
      }

      const data = await res.json();

      if (data.status === "analyzing") {
        setStatus("analyzing");
      }
      if (data.status === "complete") {
        return data.result as Record<string, unknown>;
      }
      if (data.status === "error") {
        const msg = data.error || "Processing failed";
        setStatus("error");
        setError(msg);
        throw new Error(msg);
      }
    }
  }

  return { upload, progress, status, result, error, cancel };
};
