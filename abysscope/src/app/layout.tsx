import type { Metadata } from "next";
import { Geist_Mono } from "next/font/google";
import localFont from "next/font/local";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";
import { ThemeProvider } from "@/components/theme-provider";
import { WebPushProvider } from "@/components/web-push-provider";
import { PwaFreshness } from "@/components/pwa-freshness";

/**
 * Pretendard variable — Korean + Latin in one file (~2 MB woff2).
 * Self-hosted via ``next/font/local`` so the dashboard renders the
 * same on a phone over Tailscale even when CDN access is restricted,
 * and Next.js handles preload + size-adjust automatically.
 */
const pretendard = localFont({
  src: "./fonts/PretendardVariable.woff2",
  variable: "--font-pretendard",
  display: "swap",
  weight: "45 920",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Abysscope",
  description: "abyss dashboard",
  // ``manifest`` resolves to ``/manifest.webmanifest`` (served by
  // ``app/manifest.ts``) so the browser knows the PWA name, icons,
  // start URL, and standalone display mode. Together with the Apple
  // meta tags below this is the minimum surface iOS Safari needs to
  // let "Add to Home Screen" install the dashboard as a PWA.
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Abyss",
  },
  icons: {
    icon: [
      { url: "/favicon-16x16.png", sizes: "16x16", type: "image/png" },
      { url: "/favicon-32x32.png", sizes: "32x32", type: "image/png" },
      { url: "/android-chrome-192x192.png", sizes: "192x192", type: "image/png" },
      { url: "/android-chrome-512x512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/*
          Paint the document background dark from the very first byte
          so iOS PWA cold starts (and ordinary browser navigations)
          never flash a frame of white between the OS splash and our
          first React paint. Matches the PWA manifest
          ``background_color`` and the LogoSplash inline color.
          Inline ``<style>`` rather than relying on globals.css so
          there's no stylesheet load race.
        */}
        <style>{"html,body{background-color:#131313;}"}</style>
      </head>
      <body
        className={`${pretendard.variable} ${geistMono.variable} antialiased`}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          {/*
            ``WebPushProvider`` mounts the single ``useWebPush``
            instance at the top of the React tree so visibility
            tracking + notification-click routing work on every page,
            not just the one that happens to render the bell toggle.
          */}
          <WebPushProvider>
            {/*
              ``PwaFreshness`` forces a network reload when the iOS
              standalone shell restores us from BFCache (or wakes up
              after being hidden for too long). Without this, the
              user sees yesterday's UI until they pull-to-refresh.
            */}
            <PwaFreshness />
            <div className="flex h-screen">
              <Sidebar />
              <main className="flex-1 overflow-auto p-6">{children}</main>
            </div>
          </WebPushProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
