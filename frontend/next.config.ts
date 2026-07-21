import type { NextConfig } from "next";

const apiProxyTarget = (process.env.TRIP_API_PROXY_TARGET || "http://127.0.0.1:8000").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  // The app is commonly QA'd through 127.0.0.1 while Next serves localhost.
  // Keep dev cross-origin asset requests explicit for newer Next versions.
  allowedDevOrigins: ["127.0.0.1"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiProxyTarget}/:path*`,
      },
    ];
  },
};

export default nextConfig;
