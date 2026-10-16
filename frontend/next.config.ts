import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep demo SSR, client chunks, and dev locks separate from the regular server.
  distDir: process.env.DEMO_MODE === "true" ? ".next/demo" : ".next",
};

export default nextConfig;
