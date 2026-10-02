"use client";
import { use } from "react";
import { useAuth, useSettings } from "@/components/BrandProvider";
import { LoginForm } from "@/components/Nav";
import QrCode, { originUrl } from "@/components/QrCode";
import { useApi } from "@/lib/api";

/** Printable station signs: one per page. Use the browser's Print (letter or A4, portrait). */
export default function QrSigns({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { auth, isStaff } = useAuth();
  const { settings } = useSettings();
  const { data: c } = useApi<any>(`/api/courses/${id}`);
  if (auth && !isStaff) return <main className="max-w-md mx-auto py-16 px-4"><LoginForm /></main>;
  if (!c?.data) return <main className="p-8">Loading...</main>;
  const d = c.data;
  const codes = d.qr_codes || {};
  const signs = [
    { id: "BOOTH", title: "START and FINISH", sub: "Scan when you start and when you finish, then rest the sensor for 10 seconds." },
    ...d.stations.map((s: any) => ({ id: s.id, title: `Station ${s.number}`, name: s.name, sub: "Scan this code, then set the sensor down here and keep it still for 10 seconds." })),
  ].filter((s) => codes[s.id]);
  const brand = settings?.branding;

  return (
    <div className="qr-print">
      <style>{`
        @media print {
          @page { margin: 12mm; }
          body { background: #fff !important; }
          .no-print { display: none !important; }
          .sign { page-break-after: always; break-after: page; border: none !important; }
        }
        .qr-print .sign { background: #fff; color: #111; }
      `}</style>
      <div className="no-print p-6 flex items-center gap-4 flex-wrap">
        <div><div className="text-2xl font-bold">QR signs: {c.name} v{c.version}</div>
          <div className="text-muted">One sign per page. Codes stay the same when the course is re-mapped or versioned, so signs only need printing once. They work while this course is the active one.</div></div>
        <button className="btn btn-primary" onClick={() => window.print()}>Print</button>
      </div>
      {signs.map((s) => (
        <section key={s.id} className="sign mx-auto my-6 max-w-[190mm] border border-line rounded-xl p-10 text-center flex flex-col items-center gap-6">
          <div className="text-xl font-bold tracking-widest uppercase" style={{ color: "#555" }}>{brand?.company || "BDAS"} · {brand?.event_name || "Sensor Scavenger Hunt"}</div>
          <div className="text-6xl font-black">{s.title}</div>
          {s.name && s.name !== s.title && <div className="text-3xl font-semibold">{s.name}</div>}
          <QrCode text={originUrl(`/s/${codes[s.id]}`)} size={360} />
          <div className="text-2xl max-w-[150mm]">{s.sub}</div>
          <div className="text-sm" style={{ color: "#777" }}>Scan with your phone camera. No app needed.</div>
        </section>
      ))}
    </div>
  );
}
