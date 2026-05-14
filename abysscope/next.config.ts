import type { NextConfig } from "next";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// ``__dirname`` is undefined in ESM-compiled TS configs, so resolving
// the workspace root through it leaked an "abysscope/abysscope" build
// path on the last attempt. Derive the directory from
// ``import.meta.url`` instead — that always points at the file.
const here = dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  devIndicators: false,
  // Pin the workspace root so Next does not climb past abysscope and
  // pick up ``~/package-lock.json`` when multiple lockfiles exist.
  // Without this the production build silently collapses to a
  // ``pages``-only output that ignores everything under ``app/``.
  turbopack: {
    root: resolve(here),
  },
};

export default nextConfig;
