"use client";
import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import { HuntFaq, progress, RestTimer, stationLabel, useTerms } from "@/components/HuntGuide";
import PhoneShell, { savedToken } from "@/components/PhoneShell";
import { api } from "@/lib/api";

/** Opened by scanning a sign (Home Base or a Waypoint). Records the scan and says exactly what to do next. */
export default function StationScan({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  const { home, wp, booth } = useTerms();
  const [info, setInfo] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const [state, setState] = useState<"loading" | "no-token" | "done" | "not-in-course" | "error">("loading");
  const [err, setErr] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    (async () => {
      try {
        const st = await api(`/api/qr/station/${code}`);
        setInfo(st);
        const t = savedToken();
        setToken(t);
        if (!t) { setState("no-token"); return; }
        setResult(await api("/api/qr/scan", { json: { token: t, code } }));
        setState("done");
      } catch (e: any) {
        if (e.status === 404 && /course/.test(e.message || "")) setState("not-in-course");
        else { setErr(e.message || "Something went wrong"); setState("error"); }
      }
    })();
  }, [code]);

  const s = result?.station || info?.station;
  const isHome = s?.id === "BOOTH";
  const stations = result?.stations || info?.stations || [];
  const p = result ? progress(result.scans, stations) : null;
  const anyOrder = (result?.order_rule || info?.order_rule || "any") !== "fixed";
  // Which kind of Home Base scan is this: the start, or the finish after the waypoints?
  const homeFinish = isHome && p && p.done.size > 0;
  const nextFixed = !anyOrder && p ? p.remaining.sort((a: any, b: any) => a.number - b.number)[0] : null;

  return (
    <PhoneShell>
      {state === "loading" && <div className="text-muted">Checking in...</div>}

      {state === "error" && (
        <div className="card p-5 space-y-2">
          <div className="text-xl font-bold">That did not work</div>
          <div className="text-muted">{err}</div>
          <div>Check you have signal and scan the sign again. If it keeps happening, ask at {booth}.</div>
        </div>
      )}

      {state === "not-in-course" && (
        <div className="card p-5 space-y-2">
          <div className="text-xl font-bold">This sign is not part of today&apos;s course</div>
          <div className="text-muted">You can skip it. If you think it should count, ask at {booth}.</div>
        </div>
      )}

      {state === "no-token" && s && (
        <div className="card p-5 space-y-3 border-warn">
          <div className="text-muted">{isHome ? home : stationLabel(s, wp)}</div>
          <div className="text-2xl font-bold">We don&apos;t know who you are yet</div>
          <div>This phone has not joined the hunt. At {booth}, staff show you a personal QR code when you pick up your sensor:
            scan that one first, with this same phone, then scan this sign again.</div>
          <div className="text-sm text-muted">Already joined on another phone or browser? Use that one for every scan.</div>
        </div>
      )}

      {state === "done" && s && p && (
        <>
          <div className="card p-5 text-center border-good">
            <div className="text-4xl">✓</div>
            <div className="text-3xl font-black mt-1">{isHome ? home : stationLabel(s, wp)}</div>
            <div className="text-good mt-1">{result.duplicate ? "Already scanned (that's fine)" : "Scanned"}
              {isHome ? (homeFinish ? ": finish" : ": start") : ""}</div>
          </div>

          {/* What to do now */}
          {isHome && !homeFinish && (
            <>
              <div className="card p-5 border-brand space-y-2">
                <div className="text-xl font-bold">Step 1: start your clock</div>
                <div>Set the sensor down inside the {home} circle for 10 seconds. When you pick it up, your time starts.</div>
                <div className="text-muted">Then go to {anyOrder ? `any ${wp}` : `${wp} 1`}. At each one: scan the sign, then set the sensor down for 10 seconds.</div>
              </div>
              <RestTimer />
            </>
          )}

          {!isHome && (
            <>
              <div className="card p-5 border-brand space-y-2">
                <div className="text-xl font-bold">Now set the sensor down</div>
                <div>Flat, inside the circle, hands off, for 10 seconds. The scan says where you are; the sensor proves you stopped.</div>
              </div>
              <RestTimer />
              <div className="card p-5 space-y-2">
                <div className="text-lg font-bold">{p.done.size} of {p.total} {wp}s done</div>
                {p.allDone
                  ? <div className="text-good font-semibold">That was the last one! Head back to {home}: scan the {home} sign, set the sensor down for 10 seconds, then hand it to booth staff.</div>
                  : <div>Next: {anyOrder
                      ? <>any of {p.remaining.map((r: any) => stationLabel(r, wp)).join(", ")}.</>
                      : <>{nextFixed ? stationLabel(nextFixed, wp) : ""}.</>}</div>}
              </div>
            </>
          )}

          {homeFinish && (
            <>
              {!p.allDone && (
                <div className="card p-5 border-warn space-y-1">
                  <div className="font-bold text-warn">You still have {p.remaining.length} {wp}{p.remaining.length > 1 ? "s" : ""} to go</div>
                  <div>{p.remaining.map((r: any) => stationLabel(r, wp)).join(", ")}. Go back and get {p.remaining.length > 1 ? "them" : "it"} for a complete run,
                    or finish now (your time still counts, but a complete run ranks higher).</div>
                </div>
              )}
              <div className="card p-5 border-brand space-y-2">
                <div className="text-xl font-bold">Last step</div>
                <div>Set the sensor down inside the {home} circle for 10 seconds. That stops your clock.</div>
                <div className="font-semibold">Then hand the sensor to booth staff. They plug it in and your results appear on the big screen and on your hunt page within a minute.</div>
              </div>
              <RestTimer label={`Set the sensor down in the ${home} circle, hands off. Then tap:`} />
            </>
          )}

          {token && <Link href={`/p/${token}`} className="btn w-full justify-center">My hunt page and progress</Link>}
          <HuntFaq anyOrder={anyOrder} />
        </>
      )}
    </PhoneShell>
  );
}
