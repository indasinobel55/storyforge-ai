/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output:
    process.env.NEXT_OUTPUT_STANDALONE === "true"
      ? "standalone"
      : process.env.NEXT_OUTPUT_EXPORT === "true"
        ? "export"
        : undefined,
  trailingSlash: process.env.NEXT_OUTPUT_EXPORT === "true",
  images: { unoptimized: process.env.NEXT_OUTPUT_EXPORT === "true" },
  async rewrites() {
    if (process.env.NEXT_ALL_IN_ONE === "true") {
      return [{ source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }];
    }
    return [];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
      {
        source: "/sw.js",
        headers: [{ key: "Cache-Control", value: "no-cache, no-store, must-revalidate" }],
      },
    ];
  },
};

export default nextConfig;
