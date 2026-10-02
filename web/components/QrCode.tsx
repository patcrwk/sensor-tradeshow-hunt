"use client";
import { useEffect, useState } from "react";
import QRCode from "qrcode";

/** QR code rendered as inline SVG (crisp on screen and in print). */
export default function QrCode({ text, size = 220, className = "" }: { text: string; size?: number; className?: string }) {
  const [svg, setSvg] = useState("");
  useEffect(() => {
    QRCode.toString(text, { type: "svg", margin: 1, errorCorrectionLevel: "M", color: { dark: "#000000", light: "#ffffff" } })
      .then(setSvg).catch(() => setSvg(""));
  }, [text]);
  return (
    <div className={`bg-white p-2 rounded-lg inline-block ${className}`} style={{ width: size, height: size }}
      dangerouslySetInnerHTML={{ __html: svg.replace("<svg ", `<svg width="${size - 16}" height="${size - 16}" `) }} />
  );
}

export function originUrl(path: string): string {
  if (typeof window === "undefined") return path;
  return `${window.location.origin}${path}`;
}
