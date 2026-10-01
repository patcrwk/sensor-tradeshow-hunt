"use client";
import { createContext, useContext, useEffect } from "react";
import { useApi } from "@/lib/api";

type Settings = {
  branding: { event_name: string; company: string; company_full?: string; primary: string; accent: string; logo_url: string | null; tagline: string };
  kiosk: { panels: string[]; seconds_per_panel: number; story_recording_ids: number[] };
  watch_folder: string;
  auto_publish: boolean;
  active_course_id: number | null;
  event: { id: number; name: string; created_at: number };
};

const Ctx = createContext<{ settings: Settings | null; reload: () => void }>({ settings: null, reload: () => {} });

export function useSettings() {
  return useContext(Ctx);
}

export default function BrandProvider({ children }: { children: React.ReactNode }) {
  const { data, reload } = useApi<Settings>("/api/settings", ["settings", "course", "reset"]);
  useEffect(() => {
    if (!data) return;
    const r = document.documentElement.style;
    if (data.branding.primary) r.setProperty("--brand", data.branding.primary);
    if (data.branding.accent) r.setProperty("--accent", data.branding.accent);
    document.title = `${data.branding.company || "BDAS"} | ${data.branding.event_name || "Sensor Scavenger Hunt"}`;
  }, [data]);
  return <Ctx.Provider value={{ settings: data, reload }}>{children}</Ctx.Provider>;
}
