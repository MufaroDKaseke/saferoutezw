import type { NextConfig } from "next";

// The FastAPI backend does not enable CORS, and this task must not modify it.
// In `api` data mode the browser therefore talks to this app's own origin under
// `/backend/*`, and Next forwards the request to NEXT_PUBLIC_API_URL.
const apiOrigin = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${apiOrigin}/:path*` }];
  },
};

export default nextConfig;
