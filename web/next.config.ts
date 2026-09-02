import type { NextConfig } from "next";

function configuredApiOrigin() {
  const raw = process.env.NEXT_PUBLIC_SECURESWIPE_API_URL?.trim();
  if (!raw) return null;
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error("NEXT_PUBLIC_SECURESWIPE_API_URL must be an absolute HTTP(S) origin.");
  }
  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    parsed.username ||
    parsed.password ||
    parsed.pathname !== "/" ||
    parsed.search ||
    parsed.hash
  ) {
    throw new Error("NEXT_PUBLIC_SECURESWIPE_API_URL must be an absolute HTTP(S) origin.");
  }
  return parsed.origin;
}

const apiOrigin = configuredApiOrigin();
const isDevelopment = process.env.NODE_ENV !== "production";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // The documented visual-review URL uses 127.0.0.1 while Next binds its dev
  // server as localhost. Next 16 otherwise blocks the client chunks as a
  // cross-origin development request, leaving server-rendered controls inert.
  // This option is consulted only by `next dev`.
  allowedDevOrigins: isDevelopment ? ["127.0.0.1"] : undefined,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=()",
          },
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "base-uri 'self'",
              "font-src 'self' data: https://fonts.gstatic.com",
              "form-action 'self'",
              "frame-ancestors 'none'",
              "img-src 'self' data: blob:",
              "object-src 'none'",
              // React's development build and Turbopack's HMR runtime both need
              // eval(). Without it hydration fails in `next dev` and every client
              // component silently becomes inert. Production stays strict.
              isDevelopment
                ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
                : "script-src 'self' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              [
                "connect-src 'self'",
                apiOrigin,
                "https://fonts.googleapis.com",
                "https://fonts.gstatic.com",
              ]
                .filter(Boolean)
                .join(" "),
              "upgrade-insecure-requests",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
