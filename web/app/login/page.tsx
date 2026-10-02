"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import Nav, { LoginForm } from "@/components/Nav";

function Inner() {
  const router = useRouter();
  const next = useSearchParams().get("next") || "/hunt";
  return <LoginForm onDone={() => router.push(next.startsWith("/") ? next : "/hunt")} />;
}

export default function Login() {
  return (
    <>
      <Nav />
      <main className="mx-auto max-w-md px-4 py-16"><Suspense><Inner /></Suspense></main>
    </>
  );
}
