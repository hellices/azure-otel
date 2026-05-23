import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produce a small standalone server for the Docker image
  output: "standalone",
  reactStrictMode: true,
  // Proxy /api/* to the Python backend inside the cluster.
  // In AGFC mode the gateway intercepts /api before it reaches Next.js,
  // so this rewrite only activates in LoadBalancer (no-gateway) mode.
  rewrites: async () => [
    {
      source: "/api/:path*",
      destination: `${process.env.PYTHON_INTERNAL_URL || "http://localhost:8000"}/:path*`,
    },
  ],
};

export default nextConfig;
