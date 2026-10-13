"use client";
import { useEffect, useRef, useState } from "react";
import { useSettings } from "./BrandProvider";

/* Shared pieces for the participant phone pages: wording, progress through the
   hunt (from the participant's QR scans), the 10-second rest timer and the FAQ.
   The goal is that nobody needs to come back to the booth to ask what to do. */

export type Scan = { station: string; station_name?: string; at: number };
export type PubStation = { id: string; number: number; name: string; required?: boolean };

export function useTerms() {
  const { settings } = useSettings();
  const b = settings?.branding;
  return {
    home: b?.home_term || "Home Base",
    wp: b?.station_term || "Waypoint",
    booth: b?.booth_label || "the booth",
  };
}

export function stationLabel(s: PubStation, wp: string) {
  const def = `Station ${s.number}`;
  return s.name && s.name !== def && s.name !== `${wp} ${s.number}` ? `${wp} ${s.number}: ${s.name}` : `${wp} ${s.number}`;
}

/** Where the participant is in the hunt, from their scans. */
export function progress(scans: Scan[], stations: PubStation[]) {
  const sorted = [...scans].sort((a, b) => a.at - b.at);
  const firstWp = sorted.findIndex((s) => s.station !== "BOOTH");
  const started = sorted.some((s, i) => s.station === "BOOTH" && (firstWp < 0 || i < firstWp));
  const finished = firstWp >= 0 && sorted.some((s, i) => s.station === "BOOTH" && i > firstWp);
  const done = new Set(sorted.filter((s) => s.station !== "BOOTH").map((s) => s.station));
  const required = stations.filter((s) => s.required !== false);
  const remaining = required.filter((s) => !done.has(s.id));
  return { started, finished, done, remaining, total: required.length, allDone: remaining.length === 0 };
}

/** Big 10-second countdown: hands off while it runs. */
export function RestTimer({ seconds = 10, label }: { seconds?: number; label?: string }) {
  const [left, setLeft] = useState<number | null>(null);
  const timer = useRef<any>(null);
  useEffect(() => () => clearInterval(timer.current), []);
  const start = () => {
    clearInterval(timer.current);
    const end = Date.now() + seconds * 1000;
    setLeft(seconds);
    timer.current = setInterval(() => {
      const l = Math.max(0, Math.ceil((end - Date.now()) / 1000));
      setLeft(l);
      if (l === 0) {
        clearInterval(timer.current);
        try { navigator.vibrate?.([200, 100, 200]); } catch {}
      }
    }, 200);
  };
  const running = left !== null && left > 0;
  const finished = left === 0;
  const pct = left === null ? 0 : ((seconds - left) / seconds) * 100;
  return (
    <div className="card p-5 text-center space-y-3" style={{ borderColor: finished ? "var(--good)" : running ? "var(--brand)" : undefined }}>
      {!running && !finished && (
        <>
          <div className="text-muted">{label || "Set the sensor down inside the circle, flat, hands off. Then tap:"}</div>
          <button className="btn btn-primary w-full justify-center text-xl py-4" onClick={start}>Start 10-second timer</button>
        </>
      )}
      {running && (
        <>
          <div className="text-muted">Don&apos;t touch the sensor or the table</div>
          <div className="text-7xl font-black tabular text-brand">{left}</div>
          <div className="h-2 rounded bg-panel-2 overflow-hidden"><div className="h-full bg-brand transition-all" style={{ width: `${pct}%` }} /></div>
        </>
      )}
      {finished && (
        <>
          <div className="text-5xl">✓</div>
          <div className="text-2xl font-bold text-good">Done! Pick up your sensor.</div>
          <button className="text-sm text-muted underline" onClick={start}>Not sure it stayed still? Run the timer again</button>
        </>
      )}
    </div>
  );
}

export function HuntFaq({ anyOrder = true }: { anyOrder?: boolean }) {
  const { home, wp, booth } = useTerms();
  const qa: [string, string][] = [
    [`Do I have to visit the ${wp}s in order?`, anyOrder ? `No, any order works. Just visit every one and finish at ${home}.` : `Yes: go in number order, 1, 2, 3 and so on, then back to ${home}.`],
    ["Can I hold the sensor while I count?", "No. Set it down flat inside the circle and take your hand away. The sensor can tell the difference between resting on a table and being held, and a held sensor does not count."],
    ["How long do I leave it?", "10 seconds, hands off. Use the timer on the scan page, then pick it up and keep going."],
    ["I scanned but forgot to set the sensor down (or picked it up too early).", "Set it down again for 10 seconds at the same sign. You do not need to scan again."],
    ["I set the sensor down but forgot to scan.", "Scan the sign now, then set the sensor down for another 10 seconds."],
    ["The scan page says it does not know me.", `Open your hunt page with the link at the bottom of any scan page, or scan your personal code again at ${booth}. Use the same phone and browser for every scan.`],
    ["When does my time start and stop?", `It starts when you pick the sensor up after resting it at ${home}, and stops when you set it down back at ${home}. Time spent resting at ${wp}s counts.`],
    ["What happens at the end?", `After your last ${home} rest, hand the sensor to booth staff. They plug it in and your results appear on the big screen and on your hunt page within a minute.`],
  ];
  return (
    <details className="card p-4">
      <summary className="font-bold cursor-pointer">Questions?</summary>
      <div className="mt-3 space-y-3">
        {qa.map(([q, a]) => <div key={q}><div className="font-semibold">{q}</div><div className="text-muted text-sm">{a}</div></div>)}
      </div>
    </details>
  );
}
