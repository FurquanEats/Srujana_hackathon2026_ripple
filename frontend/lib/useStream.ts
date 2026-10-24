"use client";

import { useEffect, useRef, useState } from "react";

import { WS_URL, type CaseSummary, type ScoredTransaction, type StreamEvent } from "./api";

const FEED_SIZE = 40;

/** Live scored transactions, case updates and engine stats from /ws/stream, reconnecting if the API restarts. */
export function useStream() {
  const [feed, setFeed] = useState<ScoredTransaction[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [lastCase, setLastCase] = useState<CaseSummary | null>(null);
  const [connected, setConnected] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const retry = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(WS_URL);
      socket.onopen = () => setConnected(true);
      socket.onclose = () => {
        setConnected(false);
        if (!closed) retry.current = setTimeout(connect, 2000);
      };
      socket.onmessage = (message) => {
        const event: StreamEvent = JSON.parse(message.data);
        setUpdatedAt(new Date());
        if (event.type === "txn" && event.txn) {
          const txn = event.txn;
          setFeed((prev) => [txn, ...prev].slice(0, FEED_SIZE));
        } else if (event.type === "case" && event.case) {
          setLastCase(event.case);
        } else if (event.type === "stats" && event.stats) {
          setStats(event.stats);
        }
      };
    };
    connect();
    return () => {
      closed = true;
      if (retry.current) clearTimeout(retry.current);
      socket?.close();
    };
  }, []);

  return { feed, stats, lastCase, connected, updatedAt };
}
