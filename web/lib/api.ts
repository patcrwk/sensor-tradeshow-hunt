"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export function apiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (typeof window === "undefined") return "http://127.0.0.1:8000";
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, msg: string) {
    super(msg);
    this.status = status;
  }
}

export async function api<T = any>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const opts: RequestInit = { ...init };
  if (init?.json !== undefined) {
    opts.body = JSON.stringify(init.json);
    opts.headers = { "Content-Type": "application/json", ...(init.headers || {}) };
    opts.method = init.method || "POST";
  }
  const r = await fetch(apiBase() + path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {}
    throw new ApiError(r.status, msg);
  }
  const ct = r.headers.get("content-type") || "";
  return (ct.includes("json") ? r.json() : (r.text() as any)) as Promise<T>;
}

export async function upload<T = any>(path: string, form: FormData): Promise<T> {
  return api<T>(path, { method: "POST", body: form });
}

// One shared EventSource per page. Browsers allow only ~6 connections per host,
// so a stream per hook would starve ordinary fetches.
type Msg = { kind: string; [k: string]: any };
const listeners = new Set<(m: Msg) => void>();
let shared: EventSource | null = null;
let retryTimer: any = null;

function ensureStream() {
  if (shared || typeof window === "undefined") return;
  shared = new EventSource(apiBase() + "/api/stream");
  shared.onmessage = (e) => {
    let m: Msg;
    try { m = JSON.parse(e.data); } catch { return; }
    listeners.forEach((fn) => { try { fn(m); } catch {} });
  };
  shared.onerror = () => {
    shared?.close();
    shared = null;
    clearTimeout(retryTimer);
    retryTimer = setTimeout(() => { if (listeners.size) ensureStream(); }, 3000);
  };
}

/** Subscribe to server-sent events. The callback receives parsed messages. */
export function useEvents(onMessage: (m: Msg) => void) {
  const ref = useRef(onMessage);
  ref.current = onMessage;
  useEffect(() => {
    const fn = (m: Msg) => ref.current(m);
    listeners.add(fn);
    ensureStream();
    return () => {
      listeners.delete(fn);
      if (!listeners.size) { shared?.close(); shared = null; }
    };
  }, []);
}

/** Fetch JSON, refetch on demand or when an SSE message of the given kinds arrives. */
export function useApi<T = any>(path: string | null, kinds: string[] = [], intervalMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      setData(await api<T>(path));
      setError(null);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!intervalMs) return;
    const t = setInterval(load, intervalMs);
    return () => clearInterval(t);
  }, [load, intervalMs]);
  const kindsKey = kinds.join(",");
  useEvents((m) => { if (kindsKey && kindsKey.split(",").includes(m.kind)) load(); });
  return { data, error, loading, reload: load, setData };
}
