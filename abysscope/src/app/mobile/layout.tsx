import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

/**
 * Mobile route layout.
 *
 * The root layout still mounts ``<Sidebar /> + <main className="...p-6">``
 * in a flex shell; ``Sidebar`` short-circuits to ``null`` on
 * ``/mobile/*`` so the body collapses to just the main slot. We then
 * cancel the parent's ``p-6`` padding with ``-m-6`` and grow to the
 * dynamic viewport (``h-dvh`` — handles iOS Safari's collapsing
 * address bar properly, unlike ``100vh`` which is famously broken
 * there). Earlier revisions used ``position: fixed`` to escape the
 * layout entirely, but iOS Safari pushes ``fixed`` elements off
 * screen when the soft keyboard opens, which is the "blank page on
 * mobile" symptom we hit during real-device testing.
 */

export const metadata: Metadata = {
  title: "Abyss Mobile",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#131313" },
  ],
  viewportFit: "cover",
};

export default function MobileLayout({ children }: { children: ReactNode }) {
  return (
    <div
      className="-m-6 flex h-dvh flex-col bg-background text-foreground"
      style={{
        paddingTop: "env(safe-area-inset-top)",
        paddingBottom: "env(safe-area-inset-bottom)",
        paddingLeft: "env(safe-area-inset-left)",
        paddingRight: "env(safe-area-inset-right)",
      }}
    >
      {children}
    </div>
  );
}
