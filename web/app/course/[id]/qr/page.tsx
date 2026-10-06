"use client";
import { use } from "react";
import { useAuth } from "@/components/BrandProvider";
import { LoginForm } from "@/components/Nav";
import SignSheet, { Sign } from "@/components/SignSheet";
import { useApi } from "@/lib/api";

/** Signs for a mapped course's stations. */
export default function CourseSigns({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { auth, isStaff } = useAuth();
  const { data: c } = useApi<any>(`/api/courses/${id}`);
  if (auth && !isStaff) return <main className="max-w-md mx-auto py-16 px-4"><LoginForm /></main>;
  if (!c?.data) return <main className="p-8">Loading...</main>;
  const codes = c.data.qr_codes || {};
  const signs: Sign[] = [
    { id: "BOOTH", kind: "home" as const, code: codes.BOOTH },
    ...c.data.stations.map((s: any) => ({ id: s.id, kind: "station" as const, number: s.number, name: s.name, code: codes[s.id] })),
  ].filter((s) => s.code);
  return <SignSheet heading={`Signs: ${c.name} v${c.version}`}
    note="One sign per page. Codes stay the same when the course is re-mapped or versioned. They work while this course is the active one." signs={signs} />;
}
