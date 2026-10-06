import type { Metadata } from "next";
import "./globals.css";
import "@fontsource/orbitron/700.css";
import "@fontsource/orbitron/800.css";
import "@fontsource/orbitron/900.css";
import "@fontsource/rajdhani/500.css";
import "@fontsource/rajdhani/600.css";
import "@fontsource/rajdhani/700.css";
import BrandProvider from "@/components/BrandProvider";

export const metadata: Metadata = {
  title: "BDAS | Big Duck Applied Sciences",
  description: "Advanced sensor analytics, reporting and understanding. Take a sensor on the scavenger hunt and see what it measured.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // suppressHydrationWarning: browser extensions (Grammarly, ruttl, ...) add attributes to <body> before React loads
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased min-h-screen" suppressHydrationWarning>
        <BrandProvider>{children}</BrandProvider>
      </body>
    </html>
  );
}
