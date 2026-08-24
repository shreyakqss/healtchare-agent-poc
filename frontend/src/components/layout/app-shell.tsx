"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Icons, type IconName } from "@/components/ui/icons";
import { IconButton } from "@/components/ui/button";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { ToastProvider } from "@/components/ui/feedback";

export interface NavItem { href: string; label: string; icon: IconName }

const PRIMARY: NavItem[] = [
  { href: "/patient", label: "Patient intake", icon: "user" },
  { href: "/doctor", label: "Doctor", icon: "stethoscope" },
  { href: "/clinic", label: "Clinic desk", icon: "building" },
];
const SECONDARY: NavItem[] = [{ href: "/admin", label: "Configuration", icon: "settings" }];

export function AppShell({ children, title, subtitle, actions, wide }: {
  children: ReactNode; title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; wide?: boolean;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const nav = (items: NavItem[]) =>
    items.map((item) => {
      const Icon = Icons[item.icon];
      const active = pathname === item.href || pathname.startsWith(item.href + "/");
      return (
        <Link
          key={item.href} href={item.href} onClick={() => setOpen(false)}
          aria-current={active ? "page" : undefined}
          className={cn(
            "flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors",
            active ? "bg-brand-soft text-brand" : "text-fg-muted hover:bg-sunken hover:text-fg",
          )}
        >
          <Icon size={18} className="shrink-0" />
          <span className="truncate">{item.label}</span>
        </Link>
      );
    });

  const sidebar = (
    <div className="flex h-full flex-col">
      <Link href="/" className="flex h-14 items-center gap-2.5 px-4" aria-label="CareFlow home">
        <Logo />
        <span className="text-[15px] font-semibold tracking-tight">CareFlow</span>
      </Link>
      <nav className="flex-1 space-y-6 px-3 pt-2" aria-label="Primary">
        <div className="space-y-0.5">{nav(PRIMARY)}</div>
        <div>
          <p className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-fg-subtle">Setup</p>
          <div className="space-y-0.5">{nav(SECONDARY)}</div>
        </div>
      </nav>
      <div className="border-t border-line px-4 py-3 text-[11px] leading-4 text-fg-subtle">
        Synthetic data only. Every AI output is reviewed by a clinician before release.
      </div>
    </div>
  );

  return (
    <ToastProvider>
      <div className="flex min-h-dvh">
        <aside className="hidden w-60 shrink-0 border-r border-line bg-surface lg:block">{sidebar}</aside>

        {open ? (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} aria-hidden="true" />
            <aside className="absolute inset-y-0 left-0 w-64 bg-surface shadow-pop">{sidebar}</aside>
          </div>
        ) : null}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface/90 px-4 backdrop-blur sm:px-6">
            <IconButton label="Open navigation" className="lg:hidden" onClick={() => setOpen(true)} icon={<Icons.menu size={20} />} />
            <div className="min-w-0 flex-1">
              {title ? <h1 className="truncate text-[15px] font-semibold leading-5">{title}</h1> : null}
              {subtitle ? <p className="truncate text-xs text-fg-muted">{subtitle}</p> : null}
            </div>
            <div className="flex items-center gap-1">
              {actions}
              <ThemeToggle />
            </div>
          </header>
          <main id="main" className={cn("mx-auto w-full flex-1 px-4 py-6 sm:px-6", wide ? "max-w-[1400px]" : "max-w-6xl")}>
            {children}
          </main>
        </div>
      </div>
    </ToastProvider>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("flex h-7 w-7 items-center justify-center rounded-md bg-brand text-brand-fg", className)} aria-hidden="true">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 12h4l3-7 4 14 3-7h4" />
      </svg>
    </span>
  );
}