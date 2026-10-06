"use client";
import { useEffect, useState } from "react";
import { downloadQrZip, downloadSignsPdf, QrItem, slugify } from "@/lib/qrzip";
import { renderSign, SignBrand, signBrand } from "@/lib/signs";
import { useSettings } from "./BrandProvider";
import { originUrl } from "./QrCode";

/** A sign as the app knows it: Home Base or a numbered station, with its QR code. */
export type Sign = { id: string; kind: "home" | "station"; number?: number; name?: string; code: string };

export function isLocalhost() {
  return typeof window !== "undefined" && /^(localhost|127\.|\[::1\])/.test(window.location.hostname);
}

export function useSignBrand(): SignBrand {
  const { settings } = useSettings();
  return signBrand(settings?.branding);
}

export function toItems(signs: Sign[], b: SignBrand): QrItem[] {
  return signs.map((s, i) => {
    const label = s.kind === "home" ? b.home_term : `${b.station_term} ${s.number}`;
    const named = s.name && !/^Station \d+$/.test(s.name) && s.name !== label ? s.name : "";
    return { kind: s.kind, number: s.number, name: named, url: originUrl(`/s/${s.code}`), label,
             slug: `${String(i).padStart(2, "0")}_${slugify(label)}${named ? "_" + slugify(named) : ""}` };
  });
}

function confirmLocal() {
  return !isLocalhost() || confirm(`You are on ${window.location.host}. These codes would send phones to this laptop, not the live site. Continue anyway?`);
}

/** Download the branded signs (PDF + PNG), bullseye artwork and plain QR codes in one zip. */
export function DownloadQrButton({ signs, zipName, className = "btn" }: { signs: Sign[]; zipName: string; className?: string }) {
  const b = useSignBrand();
  const [progress, setProgress] = useState<string | null>(null);
  return (
    <button className={className} disabled={!!progress || !signs.length} onClick={async () => {
      if (!confirmLocal()) return;
      setProgress("Preparing...");
      try { await downloadQrZip(toItems(signs, b), b, zipName, (d, t) => setProgress(`Drawing ${d} of ${t}...`)); }
      catch (e: any) { alert(`Could not build the zip: ${e.message || e}`); }
      finally { setProgress(null); }
    }}>{progress || "Download QR codes and signs (.zip)"}</button>
  );
}

/** Print-ready signs matching the show branding: preview, print, PDF and zip. */
export default function SignSheet({ heading, note, signs }: { heading: string; note: string; signs: Sign[] }) {
  const b = useSignBrand();
  const [images, setImages] = useState<string[]>([]);
  const [pdfBusy, setPdfBusy] = useState<string | null>(null);
  const key = JSON.stringify([signs, b]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const out: string[] = [];
      for (const it of toItems(signs, b)) {
        const c = await renderSign(it, b);
        out.push(c.toDataURL("image/jpeg", 0.92));
        c.width = c.height = 0;
        if (cancelled) return;
        setImages([...out]);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return (
    <div className="sign-sheet">
      <style>{`
        @media print {
          @page { size: letter; margin: 0; }
          html, body { background: #fff !important; margin: 0 !important; }
          .no-print { display: none !important; }
          .sign-page { width: 8.5in !important; height: 11in !important; margin: 0 !important; box-shadow: none !important;
                       border-radius: 0 !important; page-break-after: always; break-after: page; }
        }
      `}</style>
      <div className="no-print p-6 space-y-3 max-w-5xl mx-auto">
        <div className="text-2xl font-bold">{heading}</div>
        <div className="text-muted">{note}</div>
        <div className="flex gap-3 flex-wrap items-center">
          <button className="btn btn-primary" disabled={images.length < signs.length} onClick={() => confirmLocal() && window.print()}>
            {images.length < signs.length ? `Drawing ${images.length} of ${signs.length}...` : "Print"}</button>
          <button className="btn" disabled={!!pdfBusy} onClick={async () => {
            if (!confirmLocal()) return;
            setPdfBusy("Preparing...");
            try { await downloadSignsPdf(toItems(signs, b), b, `${slugify(heading)}.pdf`, (d, t) => setPdfBusy(`Drawing ${d} of ${t}...`)); }
            finally { setPdfBusy(null); }
          }}>{pdfBusy || "Download print-ready PDF"}</button>
          <DownloadQrButton signs={signs} zipName={`${slugify(heading)}.zip`} />
        </div>
        <div className="text-sm text-muted">
          Signs are US Letter and full-bleed, like the rest of the show signage. For edge-to-edge prints use the PDF at a print
          shop; on an office printer choose &quot;fit to page&quot;.
        </div>
        {isLocalhost() && (
          <div className="card p-3 border-warn text-warn">
            Warning: you are on {window.location.host}. These codes point to this address, which phones cannot open.
            Open this page on the live site before printing.
          </div>
        )}
      </div>
      <div className="flex flex-col items-center gap-8 pb-10">
        {images.map((src, i) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img key={i} src={src} alt={`sign ${i + 1}`} className="sign-page shadow-2xl rounded-md" style={{ width: "min(8.5in, 92vw)" }} />
        ))}
      </div>
    </div>
  );
}

/** Signs for the planned stations (Admin > Printable QR codes). */
export function planSigns(plan: any): Sign[] {
  if (!plan) return [];
  const out: Sign[] = [];
  if (plan.codes?.BOOTH) out.push({ id: "BOOTH", kind: "home", code: plan.codes.BOOTH });
  for (let i = 1; i <= (plan.count || 0); i++) {
    const sid = `S${i}`;
    if (plan.codes?.[sid]) out.push({ id: sid, kind: "station", number: i, name: plan.names?.[sid], code: plan.codes[sid] });
  }
  return out;
}
