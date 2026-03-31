import { useCallback, useEffect, useRef, useState } from "react";

export type CameraStatus = "loading" | "active" | "off" | "denied";

interface UseCameraReturn {
  /** Attach this callback ref to a <video> element. Auto-assigns srcObject. */
  videoRef: React.RefCallback<HTMLVideoElement>;
  /** Current camera lifecycle status. */
  status: CameraStatus;
  /** Convenience: true when the camera feed is live. */
  isEnabled: boolean;
  /** Toggle camera on/off. If permission was denied, re-requests it. */
  toggleCamera: () => void;
  /** Explicitly request camera permission and start the feed. */
  startCamera: () => Promise<void>;
}

export function useCamera(): UseCameraReturn {
  const internalRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [status, setStatus] = useState<CameraStatus>("loading");

  /* ── Callback ref: auto-attach stream when a <video> is (re-)mounted ── */

  const videoRef = useCallback((node: HTMLVideoElement | null) => {
    internalRef.current = node;
    if (node && streamRef.current) {
      node.srcObject = streamRef.current;
    }
  }, []);

  /* ── Start camera ──────────────────────────────────── */

  const startCamera = useCallback(async () => {
    setStatus("loading");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      streamRef.current = stream;

      // Attach stream to video element if already mounted
      if (internalRef.current) {
        internalRef.current.srcObject = stream;
      }
      setStatus("active");
    } catch (err: unknown) {
      // NotAllowedError = user denied permission
      const name = err instanceof DOMException ? err.name : "";
      setStatus(name === "NotAllowedError" ? "denied" : "off");
    }
  }, []);

  /* ── Stop camera ───────────────────────────────────── */

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (internalRef.current) internalRef.current.srcObject = null;
    setStatus("off");
  }, []);

  /* ── Toggle ────────────────────────────────────────── */

  const toggleCamera = useCallback(() => {
    if (status === "active") {
      stopCamera();
    } else {
      startCamera();
    }
  }, [status, startCamera, stopCamera]);

  /* ── Auto-start on mount, cleanup on unmount ───────── */

  useEffect(() => {
    startCamera();
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── Keep video element in sync when status changes ── */

  useEffect(() => {
    if (internalRef.current && streamRef.current && status === "active") {
      internalRef.current.srcObject = streamRef.current;
    }
  }, [status]);

  return {
    videoRef,
    status,
    isEnabled: status === "active",
    toggleCamera,
    startCamera,
  };
}
