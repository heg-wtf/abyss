import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  devIndicators: false,
  // Pin the workspace root so Next does not climb past abysscope and
  // pick up ``~/package-lock.json`` when multiple lockfiles exist.
  // Without this the production build silently collapses to a
  // ``pages``-only output that ignores everything under ``app/``.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
