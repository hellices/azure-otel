import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produce a small standalone server for the Docker image
  output: "standalone",
  reactStrictMode: true,
};

export default nextConfig;
