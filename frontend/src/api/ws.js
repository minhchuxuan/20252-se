// React hook for the live telemetry/notification WebSocket feed.
import { useEffect, useRef } from "react";
import { getToken } from "./client";

export function useLiveFeed(onMessage, enabled = true) {
  const handlerRef = useRef(onMessage);
  handlerRef.current = onMessage;

  useEffect(() => {
    if (!enabled) return;
    const token = getToken();
    if (!token) return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${window.location.host}/ws?token=${token}`;
    let ws;
    let closed = false;
    let retry;

    const connect = () => {
      ws = new WebSocket(url);
      ws.onmessage = (e) => {
        try {
          handlerRef.current(JSON.parse(e.data));
        } catch {
          /* ignore malformed frame */
        }
      };
      ws.onclose = () => {
        if (!closed) retry = setTimeout(connect, 2000); // auto-reconnect
      };
    };
    connect();

    return () => {
      closed = true;
      clearTimeout(retry);
      if (ws) ws.close();
    };
  }, [enabled]);
}
