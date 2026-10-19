import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Isolate live E2E, demo, and regular SSR/client chunks and dev locks.
  distDir:
    process.env.E2E_LIVE === "true"
      ? ".next/e2e-live"
      : process.env.DEMO_MODE === "true"
        ? ".next/demo"
        : ".next",
};

export default nextConfig;
