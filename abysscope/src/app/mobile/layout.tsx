import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

/**
 * Mobile route layout.
 *
 * The root layout still mounts <Sidebar /> + <main> in a flex shell;
 * `Sidebar` short-circuits to `null` on `/mobile/*` so the body's flex
 * row collapses to just the main content. Mobile screens then take
 * the full viewport via the wrapper below, which also reserves
 * `env(safe-area-inset-*)` padding for iOS Safari home indicator and
 * status bar.
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
      className="fixed inset-0 flex flex-col bg-background text-foreground"
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
