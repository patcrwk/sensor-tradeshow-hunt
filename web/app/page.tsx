"use client";
import Link from "next/link";
import { Page } from "@/components/Nav";
import { useApi } from "@/lib/api";
import { useSettings } from "@/components/BrandProvider";

const CARDS = [
  { href: "/display", title: "Display", body: "Kiosk view for the big monitor. Leaderboards, crowd stats and recording stories rotate automatically." },
  { href: "/hunt", title: "Hunt", body: "Check sensors out to participants, plug them back in, confirm the match, review check-ins." },
  { href: "/course", title: "Course Setup", body: "Upload the crew's survey walk to map the stations, check venue GPS quality and publish the course." },
  { href: "/explorer", title: "Recording Explorer", body: "Open any .IDE recording: time series, frequency, shock, environment, motion and an auto-generated story." },
  { href: "/admin", title: "Admin", body: "Branding, kiosk rotation, watch folder, lead export, synthetic test data and event reset." },
];

export default function Home() {
  const { settings } = useSettings();
  const { data: health, error } = useApi<any>("/api/health", ["course", "reset"]);
  return (
    <Page>
      <div className="mb-8">
        <h1 className="text-4xl font-extrabold">{settings?.branding.event_name || "enDAQ Sensor Demo"}</h1>
        <p className="text-muted text-lg mt-2">{settings?.branding.tagline}</p>
        <div className="mt-3 text-sm">
          {error ? <span className="text-bad">Engine not reachable at port 8000. Start it with <code>make dev</code>.</span>
            : health ? <span className="text-good">Engine running. {health.active_course_id ? `Active course #${health.active_course_id}.` : "No course published yet: runs are timed START to FINISH only."}</span> : "Connecting..."}
        </div>
      </div>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {CARDS.map((c) => (
          <Link key={c.href} href={c.href} className="card p-6 hover:border-brand transition-colors">
            <div className="text-2xl font-bold mb-2">{c.title}</div>
            <div className="text-muted">{c.body}</div>
          </Link>
        ))}
      </div>
    </Page>
  );
}
