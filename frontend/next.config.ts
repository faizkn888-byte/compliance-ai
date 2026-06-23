import type { NextConfig } from "next";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "https://compliance-ai-2xa8.onrender.com";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/proxy/:path*",
        destination: `${BACKEND_URL}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
