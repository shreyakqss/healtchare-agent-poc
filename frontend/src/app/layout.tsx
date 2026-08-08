import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { api } from "@/lib/api";
import { Dot, icons } from "@/lib/ui";
import NavLinks from "./nav-links";
import ThemeToggle from "./theme-toggle";
import "./globals.css";

/**
 * Resolves the theme before first paint, so the page never flashes the wrong
 * palette. It always writes an explicit `data-theme`, which is why the CSS
 * needs only one override block instead of duplicating the dark palette for
 * `prefers-color-scheme` and for the toggle.
 */
const THEME_SCRIPT = `try{var s=localStorage.getItem("theme");document.documentElement.dataset.theme=s||(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light")}catch(e){document.documentElement.dataset.theme="light"}`;

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Healthcare Agent Platform",
  description:
    "AI-assisted patient intake, triage and clinician preparation. Synthetic data only.",
};

/** Live count for the header. The header renders even when the API is down. */
async function activeCases(): Promise<number | null> {
  try {
    const cases = await api.listCases();
    return cases.filter((c) => !["COMPLETED", "REJECTED"].includes(c.status)).length;
  } catch {
    return null;
  }
}

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const active = await activeCases();

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      // The script below sets `data-theme` before React hydrates.
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-full flex-col">
        <header className="sticky top-0 z-30 border-b border-line bg-ink/85 backdrop-blur-md">
          <nav className="mx-auto flex max-w-[112rem] items-center gap-6 px-6 py-2.5">
            <Link href="/ops" className="flex items-center gap-2.5">
              <span className="grid size-7 place-items-center rounded bg-accent/12 text-accent ring-1 ring-accent/30">
                <icons.stethoscope className="text-[16px]" />
              </span>
              <span className="text-sm font-semibold tracking-tight">
                Healthcare Agent
                <span className="ml-1.5 rounded bg-raised px-1.5 py-0.5 font-mono text-[10px] font-normal text-faint">
                  POC
                </span>
              </span>
            </Link>

            <NavLinks />

            <div className="ml-auto flex items-center gap-4">
              <span className="flex items-center gap-2 text-xs text-dim">
                <Dot tone={active ? "accent" : "neutral"} live={Boolean(active)} />
                {active === null ? "backend offline" : `${active} active cases`}
              </span>
              <span className="hidden items-center gap-1.5 rounded border border-med/30 bg-med/8 px-2.5 py-1 text-[11px] text-med lg:flex">
                <icons.shield />
                Synthetic data only
              </span>
              <ThemeToggle />
            </div>
          </nav>
        </header>

        <main className="mx-auto w-full max-w-[112rem] flex-1 px-6 py-7">{children}</main>

        <footer className="border-t border-line-soft px-6 py-3 text-center text-[11px] text-faint">
          Demonstration system. Not a medical device. No diagnosis, treatment or
          emergency guidance is produced, and every AI output is gated on clinician
          review.
        </footer>
      </body>
    </html>
  );
}
