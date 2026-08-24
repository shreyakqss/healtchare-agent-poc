import type { Metadata, Viewport } from "next";
import "./globals.css";

/** System font stack only - no next/font/google, so the build never depends on network access.
 * The stack itself is defined in globals.css (--font-sans / --font-mono). */

/** Stamp the theme before first paint so there is never a palette flash. */
const THEME_SCRIPT = `try{var s=localStorage.getItem("theme");document.documentElement.dataset.theme=s||(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light")}catch(e){document.documentElement.dataset.theme="light"}`;

export const metadata: Metadata = {
  title: { default: "CareFlow", template: "%s · CareFlow" },
  description: "AI-assisted patient intake and administrative triage. Synthetic data only.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0e6b64" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-dvh">
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