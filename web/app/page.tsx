"use client";
import Link from "next/link";
import { Page } from "@/components/Nav";
import { useApi } from "@/lib/api";
import { useSettings } from "@/components/BrandProvider";
import { fmtTime } from "@/lib/format";

const MEASURES = [
  { title: "Motion", body: "Three-axis acceleration and rotation, hundreds of times a second. Every step, turn, bump and pause." },
  { title: "Location", body: "GPS traces your route around the show, and the sensor fills in the gaps with your steps and heading when the signal drops." },
  { title: "Environment", body: "Air pressure (it can tell when you take the stairs), temperature, humidity and light, everywhere you walk." },
];

const PILLARS = [
  { title: "Analytics", body: "Vibration, frequency content, shock events, stillness, steps and position, extracted automatically from raw data." },
  { title: "Reporting", body: "Clear dashboards, leaderboards, route replays and 3D reconstructions, generated the moment a recording comes in." },
  { title: "Understanding", body: "Every result traces back to the measurement behind it, so you can see not just what happened, but how we know." },
];

const STAFF = [
  { href: "/display", title: "Display", body: "Big-screen rotation for the booth monitor." },
  { href: "/hunt", title: "Hunt", body: "Check-out, returns, run review." },
  { href: "/course", title: "Course Setup", body: "Map the stations from a survey walk." },
  { href: "/explorer", title: "Recording Explorer", body: "Analyze and replay any recording." },
  { href: "/admin", title: "Admin", body: "Branding, kiosk, leads, reset." },
];

export default function Home() {
  const { settings } = useSettings();
  const b = settings?.branding;
  const course = useApi<any>("/api/courses/active", ["course", "reset"]);
  const lbs = useApi<any>("/api/leaderboard?category=fastest&limit=1", ["leaderboard", "reset"]);
  const { data: health, error } = useApi<any>("/api/health", ["course", "reset"]);
  const stations = course.data?.data?.stations?.length;
  const par = course.data?.data?.par?.par_time_s;
  const leader = lbs.data?.rows?.[0];

  return (
    <Page>
      {/* Hero */}
      <section className="py-10 md:py-16">
        <div className="text-accent font-bold uppercase tracking-widest mb-3">{b?.company_full || "Big Duck Applied Sciences"}</div>
        <h1 className="text-5xl md:text-6xl font-black leading-tight max-w-4xl">See the world the way a sensor does.</h1>
        <p className="text-xl md:text-2xl text-muted mt-5 max-w-3xl">
          {b?.tagline || "From raw sensor data to real understanding."} Take one of our sensors on a short walk around
          the show, and we will show you everything it measured about your trip.
        </p>
      </section>

      {/* Join the hunt */}
      <section className="card p-6 md:p-8 mb-10 border-brand">
        <div className="flex flex-wrap items-baseline justify-between gap-4 mb-6">
          <h2 className="text-3xl font-extrabold">Join the {b?.event_name || "Sensor Scavenger Hunt"}</h2>
          <div className="flex gap-6 text-lg">
            {stations ? <span><b className="text-brand">{stations}</b> stations</span> : null}
            {par ? <span>Crew time to beat <b className="text-brand tabular">{fmtTime(par, 0)}</b></span> : null}
            {leader ? <span>Leader <b className="text-accent">{leader.name}</b> <span className="tabular">{fmtTime(leader.value)}</span></span> : null}
          </div>
        </div>
        <ol className="grid md:grid-cols-3 gap-5">
          {[
            ["Pick up a sensor", "Grab one at the booth. It is already recording."],
            ["Find every station", "At each marker, set the sensor down and keep it perfectly still for 10 seconds. It knows the difference between resting on a table and held in your hand."],
            ["Bring it back", "Plug it in and watch your results land on the big screen: your time, route, steps, and how steady your hands were."],
          ].map(([t, d], i) => (
            <li key={t} className="flex gap-4">
              <span className="text-5xl font-black text-brand leading-none">{i + 1}</span>
              <div><div className="text-xl font-bold">{t}</div><div className="text-muted mt-1">{d}</div></div>
            </li>
          ))}
        </ol>
      </section>

      {/* What it measures */}
      <section className="mb-10">
        <h2 className="text-2xl font-extrabold mb-4">What your sensor is measuring</h2>
        <div className="grid md:grid-cols-3 gap-4">
          {MEASURES.map((m) => (
            <div key={m.title} className="card p-6"><div className="text-xl font-bold text-brand mb-2">{m.title}</div><div className="text-muted">{m.body}</div></div>
          ))}
        </div>
      </section>

      {/* Analytics, reporting, understanding */}
      <section className="mb-12">
        <h2 className="text-2xl font-extrabold mb-1">From data to understanding</h2>
        <p className="text-muted mb-4 max-w-3xl">A sensor collects millions of numbers. {b?.company || "BDAS"} turns them into answers you can act on.</p>
        <div className="grid md:grid-cols-3 gap-4">
          {PILLARS.map((p) => (
            <div key={p.title} className="card p-6"><div className="text-xl font-bold text-accent mb-2">{p.title}</div><div className="text-muted">{p.body}</div></div>
          ))}
        </div>
        <Link href="/explorer" className="btn btn-primary mt-5">See a drone flight reconstructed from its sensor</Link>
      </section>

      {/* Staff */}
      <section className="border-t border-line pt-6">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
          <h2 className="label">Booth staff</h2>
          <div className="text-sm">
            {error ? <span className="text-bad">Engine not reachable at port 8000. Start it with <code>make dev</code>.</span>
              : health ? <span className="text-good">Engine running. {health.active_course_id ? `Active course #${health.active_course_id}.` : "No course published yet: runs are timed START to FINISH only."}</span> : "Connecting..."}
          </div>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {STAFF.map((c) => (
            <Link key={c.href} href={c.href} className="card p-4 hover:border-brand transition-colors">
              <div className="font-bold">{c.title}</div>
              <div className="text-sm text-muted">{c.body}</div>
            </Link>
          ))}
        </div>
      </section>
    </Page>
  );
}
