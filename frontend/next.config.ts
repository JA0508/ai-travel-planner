import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The app is commonly QA'd through 127.0.0.1 while Next serves localhost.
  // Keep dev cross-origin asset requests explicit for newer Next versions.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
