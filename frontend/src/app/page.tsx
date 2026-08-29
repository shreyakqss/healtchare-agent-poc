import Link from "next/link";
import { currentUser } from "@/lib/auth";
import { serverApi } from "@/lib/api/server";
import { Logo } from "@/components/layout/app-shell";
import { Icons } from "@/components/ui/icons";
import { Badge } from "@/components/ui/badge";

const ROLES = [
  { role: "patient" as const, href: "/patient", icon: Icons.user, title: "Patient sign in", body: "Tell the intake assistant what brings you in. A clinician reviews everything before any decision is made." },
  { role: "clinician" as const, href: "/doctor", icon: Icons.stethoscope, title: "Clinician sign in", body: "Review pre-screened cases, record consultations and release visit summaries." },
  { role: "admin" as const, href: "/admin", icon: Icons.settings, title: "Administrator sign in", body: "Manage clinic configuration without receiving access to clinical case content." },
];

export default async function HomePage() {
  const [user, health] = await Promise.all([
    currentUser(),
    serverApi.health().catch(() => null),
  ]);
  const roles = user ? ROLES.filter((entry) => user.roles.includes(entry.role)) : ROLES;

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex h-14 items-center justify-between px-6">
        <div className="flex items-center gap-2.5">
          <Logo />
          <span className="text-[15px] font-semibold tracking-tight">CareFlow</span>
        </div>
        <div className="flex items-center gap-3">
          {user?.roles.includes("admin") ? <Link href="/admin" className="text-sm text-fg-muted hover:text-fg">Configuration</Link> : null}
          {user ? (
            <form action="/api/auth/logout" method="post">
              <button type="submit" className="text-sm text-fg-muted hover:text-fg">Sign out</button>
            </form>
          ) : null}
        </div>
      </header>

      <main id="main" className="mx-auto flex w-full max-w-5xl flex-1 flex-col justify-center px-6 pb-16 pt-8">
        <div className="max-w-2xl">
          <p className="text-sm font-medium text-brand">Patient intake &amp; administrative triage</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
            Structured intake, rule-based urgency, clinician review.
          </h1>
          <p className="mt-3 text-[15px] leading-7 text-fg-muted">
            A proof of concept for a clinic: the assistant collects the patient&apos;s story once, approved rules set the
            administrative priority, and nothing reaches a patient before a clinician has signed it off.
          </p>
        </div>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {roles.map((r) => (
            <Link key={r.href} href={user ? r.href : `/api/auth/login?return_to=${encodeURIComponent(r.href)}`}
              className="group rounded-lg border border-line bg-surface p-5 shadow-card transition-colors hover:border-brand-ring">
              <div className="flex h-10 w-10 items-center justify-center rounded-md bg-brand-soft text-brand">
                <r.icon size={20} />
              </div>
              <h2 className="mt-4 text-base font-semibold">{r.title}</h2>
              <p className="mt-1 text-sm leading-6 text-fg-muted">{r.body}</p>
              <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand">
                Open <Icons.arrowRight size={16} className="transition-transform group-hover:translate-x-0.5" />
              </span>
            </Link>
          ))}
        </div>

        <div className="mt-10 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-fg-subtle">
          <span className="flex items-center gap-1.5"><Icons.shield size={14} /> Synthetic data only, no real patient information</span>
          <Badge tone={health ? "success" : "danger"}>{health ? "Service online" : "Service offline"}</Badge>
          {user ? <span>Signed in as <span className="text-fg-muted">{user.username ?? "CareFlow user"}</span></span> : null}
        </div>
      </main>
    </div>
  );
}
