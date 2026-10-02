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
export type Auth = { staff: boolean; required: boolean };

const Ctx = createContext<{ settings: Settings | null; reload: () => void; auth: Auth | null; reloadAuth: () => void }>(
  { settings: null, reload: () => {}, auth: null, reloadAuth: () => {} });

export function useSettings() {
  return useContext(Ctx);
}

/** Staff status. When no staff password is configured (booth laptop), everyone is staff. */
export function useAuth() {
  const { auth, reloadAuth } = useContext(Ctx);
  return { auth, reloadAuth, isStaff: !!auth?.staff };
}

export default function BrandProvider({ children }: { children: React.ReactNode }) {
  const { data, reload } = useApi<Settings>("/api/settings", ["settings", "course", "reset"]);
  const { data: auth, reload: reloadAuth } = useApi<Auth>("/api/auth/me");
  useEffect(() => {
    if (!data) return;
    const r = document.documentElement.style;
    if (data.branding.primary) r.setProperty("--brand", data.branding.primary);
    if (data.branding.accent) r.setProperty("--accent", data.branding.accent);
    document.title = `${data.branding.company || "BDAS"} | ${data.branding.event_name || "Sensor Scavenger Hunt"}`;
  }, [data]);
  return <Ctx.Provider value={{ settings: data, reload, auth, reloadAuth }}>{children}</Ctx.Provider>;
}
