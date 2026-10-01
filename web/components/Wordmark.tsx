"use client";
import { useSettings } from "./BrandProvider";

/** Brand wordmark: uploaded logo if set, otherwise the short name with the full name beside it. */
export default function Wordmark({ size = "sm" }: { size?: "sm" | "lg" }) {
  const { settings } = useSettings();
  const b = settings?.branding;
  const short = b?.company || "BDAS";
  const full = b?.company_full || "Big Duck Applied Sciences";
  if (b?.logo_url) return <img src={b.logo_url} alt={full} className={size === "lg" ? "h-16" : "h-8"} />;
  return (
    <span className="flex items-center gap-3 whitespace-nowrap">
      <span className={`font-black tracking-tight text-brand ${size === "lg" ? "text-5xl" : "text-xl"}`}>{short}</span>
      <span className={`border-l border-line pl-3 font-semibold uppercase tracking-widest text-muted leading-tight ${size === "lg" ? "text-lg" : "text-[10px] hidden sm:inline"}`}>
        {full}
      </span>
    </span>
  );
}
