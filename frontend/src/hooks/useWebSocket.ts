import { useCallback, useEffect, useRef, useState } from "react";

export type WsStatus = "connecting" | "open" | "closed" | "error";

interface UseWebSocketReturn {
  status: WsStatus;
  sendJson: (payload: object) => void;
  sendBinary: (data: ArrayBuffer) => void;
  close: () => void;
}

interface UseWebSocketOptions {
  url: string;
  onJsonMessage?: (data: Record<string, unknown>) => void;
  onBinaryMessage?: (buffer: ArrayBuffer) => void;
  onOpen?: () => void;
  onClose?: () => void;
  enabled?: boolean;
}

export function useWebSocket({
  url,
  onJsonMessage,
  onBinaryMessage,
  onOpen,
  onClose,
  enabled = true,
}: UseWebSocketOptions): UseWebSocketReturn {
  const ws = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<WsStatus>("connecting");

  // Keep stable refs for callbacks so the effect doesn't re-run on every render
  const onJsonRef = useRef(onJsonMessage);
  const onBinaryRef = useRef(onBinaryMessage);
  const onOpenRef = useRef(onOpen);
  const onCloseRef = useRef(onClose);
  onJsonRef.current = onJsonMessage;
  onBinaryRef.current = onBinaryMessage;
  onOpenRef.current = onOpen;
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!enabled || !url) return;

    const socket = new WebSocket(url);
    socket.binaryType = "arraybuffer";
    ws.current = socket;
    setStatus("connecting");

    socket.onopen = () => {
      setStatus("open");
      onOpenRef.current?.();
    };

    socket.onmessage = (evt) => {
      if (evt.data instanceof ArrayBuffer) {
        onBinaryRef.current?.(evt.data);
      } else if (typeof evt.data === "string") {
        try {
          const parsed = JSON.parse(evt.data) as Record<string, unknown>;
          onJsonRef.current?.(parsed);
        } catch {
          // ignore malformed text frames
        }
      }
    };

    socket.onclose = () => {
      setStatus("closed");
      onCloseRef.current?.();
    };

    socket.onerror = () => {
      setStatus("error");
    };

    return () => {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onclose = null;
      socket.onerror = null;
      if (socket.readyState < WebSocket.CLOSING) socket.close();
    };
  }, [url, enabled]);

  const sendJson = useCallback((payload: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(payload));
    }
  }, []);

  const sendBinary = useCallback((data: ArrayBuffer) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(data);
    }
  }, []);

  const close = useCallback(() => {
    ws.current?.close();
  }, []);

  return { status, sendJson, sendBinary, close };
}

