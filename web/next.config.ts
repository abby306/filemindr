import type { NextConfig } from "next";

/**
 * Dev-only convenience: proxy `/api/*` to the FastAPI backend so the browser
 * calls the same origin (no CORS friction while developing). This is NEVER a
 * correctness dependency — in production the client hits the backend directly
 * via `NEXT_PUBLIC_API_ORIGIN` with CORS enabled server-side. When an explicit
 * origin is set, we skip the rewrite so it doesn't shadow the real target.
 */
const BACKEND_ORIGIN =
  process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    if (process.env.NEXT_PUBLIC_API_ORIGIN) {
      return [];
    }
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_ORIGIN}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
