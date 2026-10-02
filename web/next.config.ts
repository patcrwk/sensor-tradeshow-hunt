import type { NextConfig } from "next";

// Hosted mode (Heroku): the browser calls /api on this same origin and Next
// forwards it to the engine running inside the dyno. Local booth mode leaves
// ENGINE_INTERNAL_URL unset and the browser talks to the engine on port 8000.
const engine = process.env.ENGINE_INTERNAL_URL;

const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // Hosted builds ship a trimmed server (web/.next/standalone) so the slug stays small
  ...(engine ? { output: "standalone" as const, outputFileTracingRoot: process.cwd() } : {}),
  // gzip would buffer the Server-Sent Events stream behind the proxy
  compress: !engine,
  experimental: {
    // .IDE recordings are often tens of MB; the proxy truncates at 10 MB by default
    middlewareClientMaxBodySize: "200mb",
    proxyTimeout: 120_000,
  },
  async rewrites() {
    return engine ? [{ source: "/api/:path*", destination: `${engine}/api/:path*` }] : [];
  },
};

export default nextConfig;
