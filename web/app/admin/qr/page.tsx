"use client";
import { useAuth } from "@/components/BrandProvider";
import { LoginForm } from "@/components/Nav";
import SignSheet, { planSigns } from "@/components/SignSheet";
import { useApi } from "@/lib/api";

/** Signs for the planned stations (Admin > Printable QR codes), printable before the course is mapped. */
export default function PlanSigns() {
  const { auth, isStaff } = useAuth();
  const { data: plan } = useApi<any>("/api/qr/plan");
  if (auth && !isStaff) return <main className="max-w-md mx-auto py-16 px-4"><LoginForm /></main>;
  if (!plan) return <main className="p-8">Loading...</main>;
  const signs = planSigns(plan);
  return <SignSheet heading={`Signs: Home Base plus ${plan.count} stations`}
    note="One sign per page. Place stations 1 to N in the order the crew will walk the survey, so the mapped course matches the signs." signs={signs} />;
}
