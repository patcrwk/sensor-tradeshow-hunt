"use client";
import { use, useEffect } from "react";
import PhoneShell, { saveToken } from "@/components/PhoneShell";
import Replay from "@/components/Replay";
import { useApi } from "@/lib/api";
import { fmtM, fmtNum, fmtTime } from "@/lib/format";

/** A participant's own page: opened from the QR code at check-out. */
export default function Me({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  useEffect(() => saveToken(token), [token]);
  const { data, error } = useApi<any>(`/api/p/${token}`, ["scan", "run", "leaderboard"], 20000);

  if (error) return <PhoneShell><div className="card p-5">This hunt link was not found. Ask at the booth for a new one.</div></PhoneShell>;
  if (!data) return <PhoneShell><div className="text-muted">Loading...</div></PhoneShell>;
  const c = data.course;
  const scanned = new Set((data.scans || []).map((s: any) => s.station));
  const res = data.result;

  return (
    <PhoneShell>
      <div>
        <div className="text-accent font-bold uppercase tracking-widest text-sm">Sensor Scavenger Hunt</div>
        <h1 className="text-3xl font-black mt-1">Hi {data.name}!</h1>
      </div>

      {data.status === "out" && (
        <>
          <div className="card p-5 border-brand">
            <div className="text-xl font-bold">You are in. Your sensor is recording.</div>
            <ol className="mt-3 space-y-2 text-muted list-decimal ml-5">
              <li>Find every station on the show floor.</li>
              {c?.uses_qr && <li>Scan the station&apos;s QR code with your phone camera.</li>}
              <li>Set the sensor down on the marker and keep it perfectly still for 10 seconds.</li>
              <li>Bring it back to the booth. Your results will appear right here.</li>
            </ol>
            {c?.par_s && <div className="mt-3">Crew time to beat: <b className="text-brand tabular">{fmtTime(c.par_s, 0)}</b></div>}
          </div>
          {c && (
            <div className="card p-5">
              <div className="flex justify-between items-baseline mb-2">
                <div className="font-bold">Stations</div>
                {c.uses_qr && <div className="text-muted text-sm">{c.stations.filter((s: any) => scanned.has(s.id)).length} of {c.stations.length} scanned</div>}
              </div>
              <ul className="space-y-1">
                {c.stations.map((s: any) => (
                  <li key={s.id} className="flex items-center gap-3">
                    <span className={`w-7 h-7 rounded-full grid place-items-center font-bold text-sm ${scanned.has(s.id) ? "bg-good text-black" : "bg-panel-2 text-muted"}`}>
                      {scanned.has(s.id) ? "✓" : s.number}
                    </span>
                    <span className={scanned.has(s.id) ? "" : "text-muted"}>{s.name}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      {(data.status === "processing" || data.status === "needs_review") && (
        <div className="card p-5">
          <div className="text-xl font-bold">{data.status === "processing" ? "Reading your sensor..." : "Almost there"}</div>
          <div className="text-muted mt-1">
            {data.status === "processing" ? "Your results will appear here in a few seconds."
              : "Our team is double-checking one of your stops. Check back in a minute."}
          </div>
        </div>
      )}

      {res && (
        <>
          <div className="card p-5 text-center border-brand">
            <div className="label">Your time</div>
            <div className="text-6xl font-black tabular text-brand mt-1">{fmtTime(res.elapsed_s)}</div>
            <div className="mt-2 text-lg">
              {res.rank ? <>#{res.rank} of {res.of} on the leaderboard</> : null}
              {!res.complete && <div className="text-warn">You missed {res.summary?.missing?.length || 0} station(s)</div>}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Tile label="Distance walked" value={fmtM(res.metrics.distance_m)} />
            <Tile label="Steps" value={fmtNum(res.metrics.steps)} sub={`${fmtNum(res.metrics.cadence_spm)} per minute`} />
            <Tile label="Steadiest hands" value={res.metrics.vibration_rms_g != null ? `${(res.metrics.vibration_rms_g * 1000).toFixed(1)} mg` : "--"} sub="vibration while walking" />
            <Tile label="Top speed" value={res.metrics.top_speed_mps != null ? `${(res.metrics.top_speed_mps * 3.6).toFixed(1)} km/h` : "--"} />
          </div>
          {c && res.route?.x?.length > 1 && (
            <div className="card p-3">
              <div className="font-bold mb-2 px-1">Your route, replayed</div>
              <Replay
                main={{ ...res.route, t0: res.start?.end ?? res.route.t[0], label: "", color: "#ffffff" }}
                duration={Math.max((res.finish?.start ?? res.route.t[res.route.t.length - 1]) - (res.start?.end ?? res.route.t[0]), 1)}
                checkins={res.checkins.filter((x: any) => x.station).map((x: any) => ({ t: x.rest_start, station: x.station }))}
                courseMap={{ courseId: c.id, booth: c.booth, stations: c.stations, background: c.background,
                  reference: c.route ? { x: c.route.x, y: c.route.y, source: c.route.source, color: "#9fb0c2", opacity: 0.3 } : null }} />
            </div>
          )}
          {res.legs?.length > 0 && (
            <div className="card p-4">
              <div className="font-bold mb-2">Your splits</div>
              {res.legs.map((l: any, i: number) => (
                <div key={i} className="flex justify-between py-1 border-b border-line last:border-0 text-sm">
                  <span>{l.from_name} to {l.to_name}</span>
                  <span className="tabular">{fmtTime(l.leg_time_s)} · {fmtM(l.distance_m)}</span>
                </div>
              ))}
            </div>
          )}
          <div className="text-muted text-sm text-center">Every number here was measured by the sensor you carried.</div>
        </>
      )}
    </PhoneShell>
  );
}

function Tile({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="card p-4">
      <div className="label">{label}</div>
      <div className="text-2xl font-bold tabular mt-1">{value}</div>
      {sub && <div className="text-xs text-muted">{sub}</div>}
    </div>
  );
}
