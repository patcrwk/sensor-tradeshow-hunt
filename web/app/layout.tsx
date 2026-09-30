import type { Metadata } from "next";
import "./globals.css";
import BrandProvider from "@/components/BrandProvider";

export const metadata: Metadata = {
  title: "enDAQ Sensor Demo",
  description: "Scavenger hunt, course mapping and recording explorer for enDAQ sensors",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen">
        <BrandProvider>{children}</BrandProvider>
      </body>
    </html>
  );
}
