import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Isolate live E2E, demo, and regular SSR/client chunks and dev locks.
  distDir:
    process.env.E2E_LIVE === "true"
      ? ".next/e2e-live"
      : process.env.DEMO_MODE === "true"
        ? ".next/demo"
        : ".next",
  async headers() {
    const isDevelopment = process.env.NODE_ENV === "development";
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
    const connectSources = ["'self'"];

    // Relative API paths use the page origin. Absolute URLs contribute only their origin.
    if (!apiUrl.startsWith("/") || apiUrl.startsWith("//")) {
      const parsed = new URL(apiUrl);

      if (
        !["http:", "https:"].includes(parsed.protocol) ||
        parsed.username ||
        parsed.password ||
        /[\s;'"*]/u.test(parsed.origin)
      ) {
        throw new Error(
          "NEXT_PUBLIC_API_URL must be an HTTP(S) URL without credentials or a same-origin path",
        );
      }

      connectSources.push(parsed.origin);
    }

    if (isDevelopment) {
      connectSources.push("ws://localhost:*", "ws://127.0.0.1:*");
    }

    // Next.js hydration/theme scripts and UI style attributes require inline support.
    const policy = [
      "default-src 'self'",
      `script-src 'self' 'unsafe-inline'${isDevelopment ? " 'unsafe-eval'" : ""}`,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "font-src 'self'",
      `connect-src ${connectSources.join(" ")}`,
      "object-src 'none'",
      "frame-src 'none'",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; ");

    return [{ source: "/:path*", headers: [{ key: "Content-Security-Policy", value: policy }] }];
  },
};

export default nextConfig;
