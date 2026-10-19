"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export function apiBase(): string {
  // Hosted mode: same origin, Next forwards /api to the engine
  if (process.env.NEXT_PUBLIC_SAME_ORIGIN_API === "1") return "";
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

export type UploadProgress = { phase: "upload" | "processing"; fraction: number; retrying?: boolean };

/** Upload a recording of any size: the file is sent in pieces (each well under the
    hosting limits), resent piece by piece if the Wi-Fi drops, then read on the
    server in the background. Resolves with the new recording's id. */
export async function uploadRecording(file: File, meta: { title: string; description: string; profile: string; in_library: boolean },
                                      onProgress: (p: UploadProgress) => void): Promise<number> {
  const job = await api<any>("/api/uploads/chunked", { json: { filename: file.name, size: file.size, ...meta } });
  const piece: number = job.chunk_bytes;
  let offset = 0;
  let failures = 0;
  onProgress({ phase: "upload", fraction: 0 });
  while (offset < file.size) {
    const end = Math.min(offset + piece, file.size);
    try {
      const r = await api<any>(`/api/uploads/chunked/${job.id}?offset=${offset}`, {
        method: "PUT", body: file.slice(offset, end), headers: { "Content-Type": "application/octet-stream" } });
      offset = r.received;
      failures = 0;
      onProgress({ phase: "upload", fraction: offset / file.size });
    } catch (e: any) {
      if (e instanceof ApiError && (e.status === 404 || e.status === 400 || e.status === 413)) throw e;
      if (++failures > 8) throw new Error(`Upload stopped at ${Math.round((offset / file.size) * 100)}%: ${e.message || "network error"}. Check the Wi-Fi and try again.`);
      onProgress({ phase: "upload", fraction: offset / file.size, retrying: true });
      await new Promise((r) => setTimeout(r, Math.min(1000 * 2 ** failures, 15000)));
      try { offset = (await api<any>(`/api/uploads/chunked/${job.id}`)).received; } catch {}
    }
  }
  let st = await api<any>(`/api/uploads/chunked/${job.id}/finish`, { method: "POST" });
  while (st.status === "processing") {
    onProgress({ phase: "processing", fraction: st.progress || 0 });
    await new Promise((r) => setTimeout(r, 1500));
    try { st = await api<any>(`/api/uploads/chunked/${job.id}`); } catch (e: any) {
      if (e instanceof ApiError && e.status === 404) throw new Error("The server restarted while reading the file. Upload it again.");
    }
  }
  if (st.status !== "done") throw new Error(st.error || "Could not read the file");
  return st.recording_id;
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
