"use client";
import QRCode from "qrcode";
import { BRAND, bullseyeSvg, canvasBytes, jpegPdf, renderBullseye, renderSign, SignBrand, SignSpec } from "./signs";

/* Download QR codes and branded signs as one zip, for printing or designing
   custom signs. The zip is written here (stored, uncompressed: the images are
   already compressed) so no zip library is needed. */

export type QrItem = SignSpec & { slug: string; label: string };

export async function downloadQrZip(items: QrItem[], b: SignBrand, zipName: string,
  onProgress?: (done: number, total: number) => void) {
  const enc = new TextEncoder();
  const files: { name: string; data: Uint8Array }[] = [];
  const pdfPages: { jpeg: Uint8Array; wPx: number; hPx: number }[] = [];
  const rows = [["sign", "name", "link", "sign_png", "bullseye_svg", "bullseye_png", "qr_svg", "qr_png"]];
  const qrOpts = { errorCorrectionLevel: "M" as const, margin: 4, color: { dark: BRAND.qrDark, light: "#ffffff" } };
  let done = 0;
  for (const it of items) {
    const sign = await renderSign(it, b);
    files.push({ name: `signs/${it.slug}.png`, data: await canvasBytes(sign, "image/png") });
    pdfPages.push({ jpeg: await canvasBytes(sign, "image/jpeg", 0.95), wPx: sign.width, hPx: sign.height });
    sign.width = sign.height = 0;                      // free the canvas memory
    const bull = await renderBullseye(it.url);
    files.push({ name: `bullseye/${it.slug}.png`, data: await canvasBytes(bull, "image/png") });
    files.push({ name: `bullseye/${it.slug}.svg`, data: enc.encode(bullseyeSvg(it.url)) });
    files.push({ name: `qr/${it.slug}.svg`, data: enc.encode(await QRCode.toString(it.url, { ...qrOpts, type: "svg" })) });
    files.push({ name: `qr/${it.slug}.png`, data: dataUrlBytes(await QRCode.toDataURL(it.url, { ...qrOpts, width: 2000 })) });
    rows.push([it.label, it.name || "", it.url, `signs/${it.slug}.png`, `bullseye/${it.slug}.svg`, `bullseye/${it.slug}.png`,
      `qr/${it.slug}.svg`, `qr/${it.slug}.png`]);
    onProgress?.(++done, items.length);
  }
  files.unshift({ name: "signs.pdf", data: jpegPdf(pdfPages) });
  files.push({ name: "codes.csv", data: enc.encode(rows.map((r) => r.map(csv).join(",")).join("\r\n") + "\r\n") });
  files.push({ name: "README.txt", data: enc.encode(readme(b)) });
  saveBytes(zip(files), zipName, "application/zip");
}

/** Print-ready PDF of the signs only. */
export async function downloadSignsPdf(items: QrItem[], b: SignBrand, name: string, onProgress?: (d: number, t: number) => void) {
  const pages: { jpeg: Uint8Array; wPx: number; hPx: number }[] = [];
  let done = 0;
  for (const it of items) {
    const c = await renderSign(it, b);
    pages.push({ jpeg: await canvasBytes(c, "image/jpeg", 0.95), wPx: c.width, hPx: c.height });
    c.width = c.height = 0;
    onProgress?.(++done, items.length);
  }
  saveBytes(jpegPdf(pages), name, "application/pdf");
}

export function saveBytes(bytes: Uint8Array, name: string, type: string) {
  const blob = new Blob([bytes as Uint8Array<ArrayBuffer>], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
}

export function slugify(s: string) {
  return s.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "code";
}

function readme(b: SignBrand) {
  return `QR codes and signs for the ${b.event_name}

signs.pdf    every sign, print-ready: US Letter, 300 dpi, one per page
signs/       the same signs as individual 2550 x 3300 PNG images
bullseye/    the QR code inside the ${b.station_term} bullseye, transparent background
             (4.1 in at 300 dpi; SVG is vector) - drop into your own layout
qr/          the plain QR codes (SVG vector, and 2000 x 2000 PNG)
codes.csv    which files belong to which sign, and the link each code opens

The signs are full-bleed (edge to edge). Print them at a print shop, or on an
office printer with "fit to page" and accept a thin white border.

If you design your own signs:
- Keep the white area around each code (the "quiet zone"); scanners need it.
- Print each code at least 3.5 cm (1.4 in) wide; bigger scans from further away.
- Dark code on a light background scans best. Do not place anything over the code.
- Each code belongs to one sign. Check the ${b.station_term} number matches codes.csv.
- Test-scan every printed sign with a phone before the show.
`;
}

function csv(v: string) {
  return /[",\r\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
}

function dataUrlBytes(d: string) {
  const b = atob(d.split(",")[1]);
  const out = new Uint8Array(b.length);
  for (let i = 0; i < b.length; i++) out[i] = b.charCodeAt(i);
  return out;
}

let CRC_TABLE: Uint32Array | null = null;
function crc32(data: Uint8Array) {
  if (!CRC_TABLE) {
    CRC_TABLE = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      CRC_TABLE[n] = c >>> 0;
    }
  }
  let crc = 0xffffffff;
  for (let i = 0; i < data.length; i++) crc = CRC_TABLE[(crc ^ data[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

/** Minimal ZIP writer (store method). */
function zip(files: { name: string; data: Uint8Array }[]): Uint8Array {
  const enc = new TextEncoder();
  const now = new Date();
  const dosTime = (now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1);
  const dosDate = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();
  const parts: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;
  for (const f of files) {
    const name = enc.encode(f.name);
    const crc = crc32(f.data);
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);
    local.setUint16(4, 20, true);
    local.setUint16(6, 0x0800, true);          // UTF-8 names
    local.setUint16(8, 0, true);               // stored
    local.setUint16(10, dosTime, true);
    local.setUint16(12, dosDate, true);
    local.setUint32(14, crc, true);
    local.setUint32(18, f.data.length, true);
    local.setUint32(22, f.data.length, true);
    local.setUint16(26, name.length, true);
    local.setUint16(28, 0, true);
    parts.push(new Uint8Array(local.buffer), name, f.data);
    const cd = new DataView(new ArrayBuffer(46));
    cd.setUint32(0, 0x02014b50, true);
    cd.setUint16(4, 20, true);
    cd.setUint16(6, 20, true);
    cd.setUint16(8, 0x0800, true);
    cd.setUint16(10, 0, true);
    cd.setUint16(12, dosTime, true);
    cd.setUint16(14, dosDate, true);
    cd.setUint32(16, crc, true);
    cd.setUint32(20, f.data.length, true);
    cd.setUint32(24, f.data.length, true);
    cd.setUint16(28, name.length, true);
    cd.setUint32(42, offset, true);
    central.push(new Uint8Array(cd.buffer), name);
    offset += 30 + name.length + f.data.length;
  }
  const cdSize = central.reduce((a, p) => a + p.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, files.length, true);
  end.setUint16(10, files.length, true);
  end.setUint32(12, cdSize, true);
  end.setUint32(16, offset, true);
  const all = [...parts, ...central, new Uint8Array(end.buffer)];
  const out = new Uint8Array(all.reduce((a, p) => a + p.length, 0));
  let o = 0;
  for (const p of all) { out.set(p, o); o += p.length; }
  return out;
}
