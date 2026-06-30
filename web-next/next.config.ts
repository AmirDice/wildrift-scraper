import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root so Next doesn't pick up the stray lockfile in the
  // user's home directory when inferring the project root.
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
