import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";

import { Providers } from "./providers";
import { AmbientBackground } from "@/components/brand/AmbientBackground";
import { ServiceWorkerRegistrar } from "@/components/pwa/ServiceWorkerRegistrar";
import { Toaster } from "@/components/ui/sonner";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Distinctive display face for headings — premium, not the default template look.
const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

export const metadata: Metadata = {
  title: {
    default: "GUMMY — Your Personal AI Operating System",
    template: "%s · GUMMY",
  },
  description:
    "GUMMY is a Personal AI Operating System: persistent memory, goals and tasks, and collaborating agents — not just a chat window.",
  // iOS ignores the web app manifest for home-screen installs and reads
  // these instead, so both are needed for the app to install everywhere.
  appleWebApp: {
    capable: true,
    title: "GUMMY",
    statusBarStyle: "black-translucent",
  },
  icons: {
    apple: "/apple-touch-icon.png",
  },
};

/**
 * `viewport-fit=cover` lets the shell reach under the notch on a phone, which
 * is what makes an installed PWA look native rather than letterboxed.
 * `maximumScale` is deliberately left unset: locking zoom breaks the app for
 * anyone who needs to magnify it.
 */
export const viewport: Viewport = {
  themeColor: "#0f1413",
  viewportFit: "cover",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} ${spaceGrotesk.variable} h-full antialiased`}
    >
      <body className="bg-background text-foreground flex min-h-full flex-col">
        <AmbientBackground />
        <Providers>{children}</Providers>
        <Toaster richColors position="top-center" />
        <ServiceWorkerRegistrar />
      </body>
    </html>
  );
}
