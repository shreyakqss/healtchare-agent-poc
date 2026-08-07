import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Healthcare Agent POC",
  description:
    "AI-assisted patient intake and clinician preparation. Synthetic data only.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
        <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <nav className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3">
            <span className="font-semibold tracking-tight">
              Healthcare Agent{" "}
              <span className="text-zinc-400 dark:text-zinc-500">POC</span>
            </span>
            <Link
              href="/"
              className="text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
            >
              Patient intake
            </Link>
            <Link
              href="/dashboard"
              className="text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
            >
              Staff dashboard
            </Link>
            <span className="ml-auto rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              Synthetic data only — not for clinical use
            </span>
          </nav>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
