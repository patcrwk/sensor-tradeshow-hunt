import type { Metadata } from "next";
import "./globals.css";
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
