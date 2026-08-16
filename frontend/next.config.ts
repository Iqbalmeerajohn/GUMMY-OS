import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root to this app so Next doesn't mis-detect it from a
  // stray lockfile elsewhere on the machine (Turbopack root inference).
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
