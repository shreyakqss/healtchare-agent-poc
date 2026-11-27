"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Icons, type IconName } from "@/components/ui/icons";
import { IconButton } from "@/components/ui/button";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { ToastProvider } from "@/components/ui/feedback";
import type { AuthUser } from "@/lib/api/types";

export interface NavItem { href: string; label: string; icon: IconName }

const PRIMARY: NavItem[] = [
  { href: "/patient", label: "Patient intake", icon: "user" },
  { href: "/doctor", label: "Doctor", icon: "stethoscope" },
];
const SECONDARY: NavItem[] = [
  { href: "/admin", label: "Configuration", icon: "settings" },
  { href: "/admin/doctors", label: "Doctors", icon: "stethoscope" },
  { href: "/admin/patients", label: "Patients", icon: "user" },
];

export function AppShell({ children, title, subtitle, actions, wide, user }: {
  children: ReactNode; title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; wide?: boolean; user: AuthUser;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const navigationDialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = navigationDialog.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const visible = (item: NavItem) => (
    (item.href === "/patient" && user.roles.includes("patient"))
    || (item.href === "/doctor" && user.roles.includes("clinician"))
    || (item.href.startsWith("/admin") && user.roles.includes("admin"))
  );
  const nav = (items: NavItem[]) =>
    items.filter(visible).map((item) => {
      const Icon = Icons[item.icon];
      // A deeper item that matches (Admin > Doctors) wins over its parent (Configuration).
      const matches = (href: string) => pathname === href || pathname.startsWith(href + "/");
      const active = matches(item.href) && !items.some((other) => other.href.startsWith(item.href + "/") && matches(other.href));
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
        {SECONDARY.some(visible) ? <div>
          <p className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-fg-subtle">Setup</p>
          <div className="space-y-0.5">{nav(SECONDARY)}</div>
        </div> : null}
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

        <dialog
          ref={navigationDialog}
          aria-label="Navigation"
          onClose={() => setOpen(false)}
          onClick={(event) => { if (event.target === event.currentTarget) setOpen(false); }}
          className="fixed inset-y-0 left-0 z-40 m-0 h-dvh max-h-none w-64 max-w-none border-0 bg-surface p-0 text-fg shadow-pop backdrop:bg-black/50 lg:hidden"
        >
          <IconButton
            autoFocus
            label="Close navigation"
            className="absolute right-2 top-2 z-10"
            onClick={() => setOpen(false)}
            icon={<Icons.x size={20} />}
          />
          <aside className="h-full">{sidebar}</aside>
        </dialog>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface/90 px-4 backdrop-blur sm:px-6">
            <IconButton label="Open navigation" className="lg:hidden" onClick={() => setOpen(true)} icon={<Icons.menu size={20} />} />
            <div className="min-w-0 flex-1">
              {title ? <h1 className="truncate text-[15px] font-semibold leading-5">{title}</h1> : null}
              {subtitle ? <p className="truncate text-xs text-fg-muted">{subtitle}</p> : null}
            </div>
            <div className="flex items-center gap-1">
              {actions}
              <span className="hidden max-w-40 truncate px-2 text-xs text-fg-muted sm:inline">
                {user.username ?? "Signed in"}
              </span>
              <form action="/api/auth/logout" method="post">
                <button type="submit" className="rounded-md px-2 py-1.5 text-xs font-medium text-fg-muted hover:bg-sunken hover:text-fg">
                  Sign out
                </button>
              </form>
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
