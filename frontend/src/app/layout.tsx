import type { Metadata, Viewport } from "next";
import { connection } from "next/server";
import Script from "next/script";
import "./globals.css";

const THEME_SCRIPT = `try{var s=localStorage.getItem("theme");document.documentElement.dataset.theme=s||(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light")}catch(e){document.documentElement.dataset.theme="light"}`;

export const metadata: Metadata = {
  title: { default: "CareFlow", template: "%s · CareFlow" },
  description: "AI-assisted patient intake and administrative triage. Synthetic data only.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0e6b64" };

export default async function RootLayout({ children }: LayoutProps<"/">) {
  await connection();
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-dvh">
        <Script id="theme-init" strategy="beforeInteractive" dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:shadow-pop"
        >
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
