"use client";
import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import PhoneShell, { savedToken } from "@/components/PhoneShell";
import { api } from "@/lib/api";

/** Opened by scanning a station's QR sign. Records the scan against the participant's run. */
export default function StationScan({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  const [station, setStation] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const [state, setState] = useState<"loading" | "no-token" | "done" | "error">("loading");
  const [err, setErr] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    (async () => {
      try {
        const st = await api(`/api/qr/station/${code}`);
        setStation(st);
        const t = savedToken();
        setToken(t);
        if (!t) { setState("no-token"); return; }
        setResult(await api("/api/qr/scan", { json: { token: t, code } }));
        setState("done");
      } catch (e: any) { setErr(e.message || "Something went wrong"); setState("error"); }
    })();
  }, [code]);

  const s = result?.station || station?.station;
  const booth = s?.id === "BOOTH";
  const count = result ? new Set(result.scans.filter((x: any) => x.station !== "BOOTH").map((x: any) => x.station)).size : 0;

  return (
    <PhoneShell>
      {state === "loading" && <div className="text-muted">Checking in...</div>}
      {state === "error" && <div className="card p-5"><div className="text-xl font-bold">That did not work</div><div className="text-muted mt-1">{err}</div></div>}
      {state === "no-token" && s && (
        <div className="card p-5 space-y-2">
          {(booth || s.name !== `Station ${s.number}`) && <div className="text-muted">{booth ? "Booth" : `Station ${s.number}`}</div>}
          <div className="text-2xl font-bold">{s.name}</div>
          <div>First, scan your personal hunt code at the booth so we know this scan is yours. Then scan this sign again.</div>
        </div>
      )}
      {state === "done" && s && (
        <>
          <div className="card p-6 text-center border-good">
            <div className="text-5xl">✓</div>
            {(booth || s.name !== `Station ${s.number}`) && <div className="text-muted mt-2">{booth ? "Start and finish" : `Station ${s.number}`}</div>}
            <div className="text-3xl font-black mt-2">{booth ? "Booth" : s.name}</div>
            <div className="text-good mt-1">{result.duplicate ? "Already scanned" : "Scanned"}</div>
          </div>
          <div className="card p-5 border-brand">
            <div className="text-xl font-bold">Now set the sensor down</div>
            <div className="text-muted mt-1">Put it on the marker and keep it perfectly still for 10 seconds. The sensor proves the stop; the scan says where you were.</div>
          </div>
          {!booth && <div className="text-center text-lg">{count} of {result.total} stations scanned</div>}
          {token && <Link href={`/p/${token}`} className="btn w-full justify-center">My hunt page</Link>}
        </>
      )}
    </PhoneShell>
  );
}
