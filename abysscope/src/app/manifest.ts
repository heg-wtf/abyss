import type { MetadataRoute } from "next";

/**
 * Web app manifest.
 *
 * Served by Next at ``/manifest.webmanifest``. ``start_url`` lands the
 * user on the mobile route tree because that is what we expect after
 * a tap from the home screen — the heavyweight desktop dashboard is
 * still one tap away through the ``Desktop UI`` link in the mobile
 * header.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Abyss",
    short_name: "Abyss",
    description: "abyss personal AI assistant",
    start_url: "/mobile/sessions",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#131313",
    theme_color: "#131313",
    icons: [
      {
        src: "/android-chrome-192x192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/android-chrome-512x512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/android-chrome-512x512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
