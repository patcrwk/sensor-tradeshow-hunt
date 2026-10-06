"use client";
import QRCode from "qrcode";

/* Station signs in the BDAS show branding (matches the partner's "Waypoint
   Bullseye" laminate sheets). One renderer draws every sign at print quality
   (US Letter, 300 dpi); the print page, the PDF and the zip all use it, so what
   you print is exactly what you download. */

export const DPI = 300;
export const PAGE_W = 8.5 * DPI;
export const PAGE_H = 11 * DPI;

export const BRAND = {
  bgTop: "#060c18",
  bgBottom: "#0b1628",
  cyan: "#45e0ff",
  navyRing: "#0e1a32",
  white: "#eff6fe",
  text: "#c9d4e3",
  title: "#eef5ff",
  qrDark: "#0b1730",
  display: "Orbitron",
  body: "Rajdhani",
};

export type SignBrand = {
  company_full: string;   // "Big Duck Applied Sciences"
  event_name: string;     // "Sensor Scavenger Hunt"
  booth_label: string;    // "BOOTH 616"
  website: string;        // "www.bigduckappliedsciences.com"
  sign_footer: string;    // "Join the scavenger hunt and see your own live telemetry!"
  home_term: string;      // "Home Base"
  station_term: string;   // "Waypoint"
};

export const DEFAULT_SIGN_BRAND: SignBrand = {
  company_full: "Big Duck Applied Sciences",
  event_name: "Sensor Scavenger Hunt",
  booth_label: "BOOTH 616",
  website: "www.bigduckappliedsciences.com",
  sign_footer: "Join the scavenger hunt and see your own live telemetry!",
  home_term: "Home Base",
  station_term: "Waypoint",
};

export function signBrand(branding: any): SignBrand {
  const b = branding || {};
  const out = { ...DEFAULT_SIGN_BRAND };
  for (const k of Object.keys(out) as (keyof SignBrand)[]) if (b[k]) out[k] = b[k];
  if (!b.company_full && b.company) out.company_full = DEFAULT_SIGN_BRAND.company_full;
  return out;
}

export type SignSpec = {
  kind: "home" | "station";
  number?: number;          // station number
  name?: string;            // optional partner / station name
  url: string;              // what the QR opens
};

// -- assets ---------------------------------------------------------------------

let assets: Promise<{ duck: HTMLImageElement }> | null = null;

/** Wait for the brand fonts and logo before drawing (canvas does not wait for them). */
export function loadAssets() {
  if (!assets) {
    assets = (async () => {
      await Promise.all([
        `900 100px ${BRAND.display}`, `800 100px ${BRAND.display}`, `700 100px ${BRAND.display}`,
        `700 100px ${BRAND.body}`, `600 100px ${BRAND.body}`, `500 100px ${BRAND.body}`,
      ].map((f) => document.fonts.load(f)));
      const duck = new Image();
      duck.src = "/brand/bdas-duck.png";
      await duck.decode().catch(() => {});
      return { duck };
    })();
  }
  return assets;
}

// -- drawing helpers ------------------------------------------------------------

const IN = (x: number) => x * DPI;

function qrMatrix(url: string) {
  const q = QRCode.create(url, { errorCorrectionLevel: "M" });
  const n = q.modules.size;
  return { n, dark: (r: number, c: number) => q.modules.get(r, c) === 1 };
}

function drawQr(ctx: CanvasRenderingContext2D, url: string, cx: number, cy: number, side: number, color = BRAND.qrDark) {
  const { n, dark } = qrMatrix(url);
  // Whole-pixel cells, so neighbouring squares meet exactly (no hairline seams in print)
  const cell = Math.max(1, Math.floor(side / n));
  const x0 = Math.round(cx - (cell * n) / 2), y0 = Math.round(cy - (cell * n) / 2);
  ctx.save();
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = color;
  ctx.beginPath();
  for (let r = 0; r < n; r++)
    for (let c = 0; c < n; c++)
      if (dark(r, c)) ctx.rect(x0 + c * cell, y0 + r * cell, cell, cell);
  ctx.fill();
  ctx.restore();
}

/** Bullseye: thin white outer ring, navy band, cyan ring, navy ring, white centre with the QR.
    Radii (inches) measured from the partner's laminate sheet. */
export function drawBullseye(ctx: CanvasRenderingContext2D, url: string, cx: number, cy: number, scale = 1) {
  const R = (inches: number) => IN(inches) * scale;
  const disc = (r: number, color: string) => { ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill(); };
  disc(R(1.99), "#f2f9ff");          // thin outer ring
  disc(R(1.96), "#0a1426");
  disc(R(1.67), BRAND.cyan);
  disc(R(1.37), BRAND.navyRing);
  disc(R(1.07), BRAND.white);
  drawQr(ctx, url, cx, cy, R(1.36));   // largest square that keeps a white quiet zone inside the circle
}

function background(ctx: CanvasRenderingContext2D, w: number, h: number) {
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, BRAND.bgTop);
  g.addColorStop(0.55, "#081120");
  g.addColorStop(1, BRAND.bgBottom);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
  // faint technical grid
  ctx.strokeStyle = "rgba(120, 170, 230, 0.055)";
  ctx.lineWidth = 2;
  const step = IN(0.26);
  for (let x = step / 2; x < w; x += step) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); }
  for (let y = step / 2; y < h; y += step) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
  // soft vignette
  const v = ctx.createRadialGradient(w / 2, h * 0.42, h * 0.2, w / 2, h * 0.5, h * 0.8);
  v.addColorStop(0, "rgba(0,0,0,0)");
  v.addColorStop(1, "rgba(0,0,0,0.35)");
  ctx.fillStyle = v;
  ctx.fillRect(0, 0, w, h);
}

function text(ctx: CanvasRenderingContext2D, s: string, x: number, y: number, font: string, color: string,
  opts: { spacing?: number; glow?: string; maxWidth?: number } = {}) {
  ctx.save();
  ctx.font = font;
  ctx.fillStyle = color;
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  if (opts.spacing) (ctx as any).letterSpacing = `${opts.spacing}px`;
  if (opts.glow) { ctx.shadowColor = opts.glow; ctx.shadowBlur = IN(0.06); }
  ctx.fillText(s, x, y, opts.maxWidth);
  ctx.restore();
}

/** Word-wrap centred text; returns the y after the last line. */
function paragraph(ctx: CanvasRenderingContext2D, s: string, cx: number, y: number, maxW: number, size: number, color: string) {
  ctx.save();
  ctx.font = `500 ${size}px ${BRAND.body}`;
  const words = s.split(/\s+/);
  const lines: string[] = [];
  let line = "";
  for (const w of words) {
    const t = line ? `${line} ${w}` : w;
    if (ctx.measureText(t).width > maxW && line) { lines.push(line); line = w; } else line = t;
  }
  if (line) lines.push(line);
  ctx.restore();
  const lh = size * 1.32;
  lines.forEach((l, i) => text(ctx, l, cx, y + i * lh, `500 ${size}px ${BRAND.body}`, color));
  return y + (lines.length - 1) * lh;
}

// -- the sign -------------------------------------------------------------------

export function homeBody(b: SignBrand) {
  return `Scan the QR code to check in and then set your sensor down inside the circle for 10 seconds. `
    + `Scan and place once to start and once to finish here and once at each other ${b.station_term}.`;
}
export const STATION_BODY = "Scan the QR code to check in and then set your sensor down inside the circle for 10 seconds.";

export async function renderSign(spec: SignSpec, b: SignBrand): Promise<HTMLCanvasElement> {
  const { duck } = await loadAssets();
  const c = document.createElement("canvas");
  c.width = PAGE_W;
  c.height = PAGE_H;
  const ctx = c.getContext("2d")!;
  const cx = PAGE_W / 2;
  background(ctx, PAGE_W, PAGE_H);

  void duck;   // the bullseye sheets carry no logo; the duck is available for other layouts

  let bullY: number;
  if (spec.kind === "home") {
    const words = b.home_term.toUpperCase().split(/\s+/);
    const lines = words.length > 1 ? [words.slice(0, Math.ceil(words.length / 2)).join(" "), words.slice(Math.ceil(words.length / 2)).join(" ")] : words;
    const size = IN(0.97);
    const first = lines.length > 1 ? IN(1.62) : IN(2.05);
    lines.forEach((l, i) => text(ctx, l, cx, first + i * IN(0.82), `800 ${size}px ${BRAND.display}`, BRAND.title,
      { spacing: IN(0.02), glow: "rgba(69,224,255,0.35)", maxWidth: IN(7.4) }));
    bullY = IN(4.68);
  } else {
    text(ctx, b.station_term.toUpperCase(), cx, IN(1.07), `700 ${IN(0.34)}px ${BRAND.body}`, "#c4cfdd", { spacing: IN(0.01) });
    text(ctx, String(spec.number ?? ""), cx, IN(3.0), `800 ${IN(1.95)}px ${BRAND.display}`, BRAND.title,
      { glow: "rgba(69,224,255,0.55)" });
    if (spec.name && spec.name !== `${b.station_term} ${spec.number}` && !/^Station \d+$/.test(spec.name)) {
      text(ctx, spec.name.toUpperCase(), cx, IN(3.42), `700 ${IN(0.26)}px ${BRAND.body}`, BRAND.cyan, { spacing: IN(0.01), maxWidth: IN(7) });
      bullY = IN(5.55);
    } else bullY = IN(5.2);
  }

  drawBullseye(ctx, spec.url, cx, bullY);

  let y = bullY + IN(2.42);
  text(ctx, "SCAN TO CHECK IN", cx, y, `700 ${IN(0.21)}px ${BRAND.body}`, BRAND.cyan, { spacing: IN(0.005) });
  y = paragraph(ctx, spec.kind === "home" ? homeBody(b) : STATION_BODY, cx, y + IN(0.38), IN(6.9), IN(0.25), BRAND.text);
  y += IN(0.42);
  text(ctx, b.sign_footer.toUpperCase(), cx, y, `700 ${IN(0.165)}px ${BRAND.body}`, "#f4f8fc", { maxWidth: IN(7.4) });
  text(ctx, `${b.booth_label.toUpperCase()}  ·  ${b.website}`, cx, y + IN(0.29), `700 ${IN(0.19)}px ${BRAND.body}`, BRAND.cyan,
    { maxWidth: IN(7.4) });
  return c;
}

/** Bullseye with the QR on a transparent background (4 x 4 in at 300 dpi), for the partner's own layouts. */
export async function renderBullseye(url: string): Promise<HTMLCanvasElement> {
  const c = document.createElement("canvas");
  c.width = c.height = IN(4.1);
  drawBullseye(c.getContext("2d")!, url, c.width / 2, c.height / 2);
  return c;
}

/** Same bullseye as vector SVG. */
export function bullseyeSvg(url: string): string {
  const { n, dark } = qrMatrix(url);
  const S = 4.1, c = S / 2, side = 1.36, cell = side / n, x0 = c - side / 2;
  let path = "";
  for (let r = 0; r < n; r++) {
    let k = 0;
    while (k < n) {
      if (!dark(r, k)) { k++; continue; }
      let e = k;
      while (e < n && dark(r, e)) e++;
      const w = (e - k) * cell;
      path += `M${(x0 + k * cell).toFixed(4)} ${(x0 + r * cell).toFixed(4)}h${w.toFixed(4)}v${(cell * 1.02).toFixed(4)}h-${w.toFixed(4)}z`;
      k = e;
    }
  }
  const circ = (r: number, f: string) => `<circle cx="${c}" cy="${c}" r="${r}" fill="${f}"/>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${S}in" height="${S}in" viewBox="0 0 ${S} ${S}">`
    + circ(1.99, "#f2f9ff") + circ(1.96, "#0a1426") + circ(1.67, BRAND.cyan) + circ(1.37, BRAND.navyRing) + circ(1.07, BRAND.white)
    + `<path d="${path}" fill="${BRAND.qrDark}" shape-rendering="crispEdges"/></svg>`;
}

export function canvasBytes(c: HTMLCanvasElement, type: "image/png" | "image/jpeg", quality?: number): Promise<Uint8Array> {
  return new Promise((resolve, reject) => c.toBlob(async (b) => {
    if (!b) return reject(new Error("could not encode image"));
    resolve(new Uint8Array(await b.arrayBuffer()));
  }, type, quality));
}

/** Minimal PDF: one full-page JPEG per page (the same format as the partner's print files). */
export function jpegPdf(pages: { jpeg: Uint8Array; wPx: number; hPx: number }[], wIn = 8.5, hIn = 11): Uint8Array {
  const enc = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const offsets: number[] = [];
  let pos = 0;
  const push = (b: Uint8Array | string) => { const u = typeof b === "string" ? enc.encode(b) : b; chunks.push(u); pos += u.length; };
  const obj = (id: number, body: () => void) => { offsets[id] = pos; push(`${id} 0 obj\n`); body(); push("\nendobj\n"); };
  const W = wIn * 72, H = hIn * 72;
  const n = pages.length;
  // ids: 1 catalog, 2 pages, then per page: page, content, image
  push("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n");
  obj(1, () => push("<< /Type /Catalog /Pages 2 0 R >>"));
  const kids = pages.map((_, i) => `${3 + i * 3} 0 R`).join(" ");
  obj(2, () => push(`<< /Type /Pages /Kids [${kids}] /Count ${n} >>`));
  pages.forEach((p, i) => {
    const pid = 3 + i * 3, cid = pid + 1, iid = pid + 2;
    obj(pid, () => push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${W} ${H}] /Contents ${cid} 0 R /Resources << /XObject << /Im${i} ${iid} 0 R >> >> >>`));
    const content = `q ${W} 0 0 ${H} 0 0 cm /Im${i} Do Q`;
    obj(cid, () => { push(`<< /Length ${content.length} >>\nstream\n`); push(content); push("\nendstream"); });
    obj(iid, () => {
      push(`<< /Type /XObject /Subtype /Image /Width ${p.wPx} /Height ${p.hPx} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${p.jpeg.length} >>\nstream\n`);
      push(p.jpeg);
      push("\nendstream");
    });
  });
  const total = 3 + n * 3;
  const xref = pos;
  push(`xref\n0 ${total}\n0000000000 65535 f \n`);
  for (let i = 1; i < total; i++) push(`${String(offsets[i]).padStart(10, "0")} 00000 n \n`);
  push(`trailer\n<< /Size ${total} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  const out = new Uint8Array(pos);
  let o = 0;
  for (const c of chunks) { out.set(c, o); o += c.length; }
  return out;
}
