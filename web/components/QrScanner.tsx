"use client";
import { useEffect, useRef, useState } from "react";
import jsQR from "jsqr";

/* In-page QR scanner, so participants never leave the hunt page to use the camera
   app. Uses the rear camera through getUserMedia (needs HTTPS) and decodes frames
   with jsQR, which works on iPhone as well as Android. */

export type ScanTarget = { kind: "station"; code: string } | { kind: "join"; token: string };

/** Accept only our own sign and join links. */
export function parseHuntUrl(text: string): ScanTarget | null {
  try {
    const u = new URL(text, window.location.origin);
    if (u.host !== window.location.host) return null;
    let m = u.pathname.match(/^\/s\/([\w-]+)\/?$/);
    if (m) return { kind: "station", code: m[1] };
    m = u.pathname.match(/^\/p\/([\w-]+)\/?$/);
    if (m) return { kind: "join", token: m[1] };
  } catch {}
  return null;
}

export default function QrScanner({ onResult, onClose }: { onResult: (t: ScanTarget) => void; onClose: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const done = useRef(false);
  const cb = useRef(onResult);
  cb.current = onResult;

  useEffect(() => {
    let stream: MediaStream | null = null;
    let raf = 0;
    let last = 0;
    (async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError("This browser cannot open the camera from a web page. Use your phone's camera app to scan the sign instead.");
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      } catch (e: any) {
        setError(e?.name === "NotAllowedError"
          ? "Camera access was blocked. Allow the camera for this site (in the browser's site settings), or use your phone's camera app to scan the sign."
          : "Could not open the camera. Use your phone's camera app to scan the sign instead.");
        return;
      }
      const v = video.current!;
      v.srcObject = stream;
      v.setAttribute("playsinline", "true");
      await v.play().catch(() => {});
      canvas.current = document.createElement("canvas");
      const tick = (now: number) => {
        raf = requestAnimationFrame(tick);
        if (done.current || now - last < 120 || v.readyState < 2) return;
        last = now;
        const w = v.videoWidth, h = v.videoHeight;
        if (!w || !h) return;
        // decode a centred square, scaled down for speed
        const side = Math.min(w, h), size = Math.min(side, 640);
        const c = canvas.current!;
        c.width = c.height = size;
        const ctx = c.getContext("2d", { willReadFrequently: true })!;
        ctx.drawImage(v, (w - side) / 2, (h - side) / 2, side, side, 0, 0, size, size);
        const img = ctx.getImageData(0, 0, size, size);
        const code = jsQR(img.data, size, size, { inversionAttempts: "dontInvert" });
        if (!code?.data) return;
        const target = parseHuntUrl(code.data);
        if (!target) { setHint("That QR code is not one of the hunt signs."); return; }
        done.current = true;
        try { navigator.vibrate?.(80); } catch {}
        cb.current(target);
      };
      raf = requestAnimationFrame(tick);
    })();
    return () => {
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  return (
    <div className="fixed inset-0 z-50 bg-black flex flex-col">
      <div className="flex items-center justify-between px-5 py-4 text-white">
        <div className="font-bold text-lg">Point at the QR code on the sign</div>
        <button className="btn" onClick={onClose}>Close</button>
      </div>
      <div className="relative flex-1 overflow-hidden">
        <video ref={video} className="absolute inset-0 w-full h-full object-cover" muted playsInline />
        <div className="absolute inset-0 grid place-items-center pointer-events-none">
          <div className="w-[70vmin] h-[70vmin] rounded-2xl border-4 border-brand shadow-[0_0_0_9999px_rgba(0,0,0,0.45)]" />
        </div>
      </div>
      <div className="px-5 py-4 text-center text-white min-h-[4rem]">
        {error ? <div className="text-warn">{error}</div> : hint ? <div className="text-warn">{hint}</div> : <div className="text-muted">Hold steady, about a hand&apos;s length away.</div>}
      </div>
    </div>
  );
}

/** "Scan next sign" button plus the scanner overlay. */
export function ScanButton({ onResult, label = "Scan next sign" }: { onResult: (t: ScanTarget) => void; label?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="btn btn-primary w-full justify-center text-xl py-4" onClick={() => setOpen(true)}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <path d="M3 7V4h3M21 7V4h-3M3 17v3h3M21 17v3h-3M7 12h10" /></svg>
        {label}
      </button>
      {open && <QrScanner onClose={() => setOpen(false)} onResult={(t) => { setOpen(false); onResult(t); }} />}
    </>
  );
}
