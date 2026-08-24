import Link from "next/link";
import { healthApi, safe } from "@/lib/api";
import { Logo } from "@/components/layout/app-shell";
import { Icons } from "@/components/ui/icons";
import { Badge } from "@/components/ui/badge";

const ROLES = [
  { href: "/patient", icon: Icons.user, title: "I am a patient", body: "Tell the intake assistant what brings you in. A clinician reviews everything before any decision is made." },
  { href: "/doctor", icon: Icons.stethoscope, title: "I am a doctor", body: "Review pre-screened cases, record consultations and release visit summaries." },
  { href: "/clinic", icon: Icons.building, title: "I work the clinic desk", body: "Live queue, priorities, routing and the audit trail for every case." },
];

export default async function HomePage() {
  const health = await safe(healthApi.get(), null);

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex h-14 items-center justify-between px-6">
        <div className="flex items-center gap-2.5">
          <Logo />
          <span className="text-[15px] font-semibold tracking-tight">CareFlow</span>
        </div>
        <Link href="/admin" className="text-sm text-fg-muted hover:text-fg">Configuration</Link>
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

        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          {ROLES.map((r) => (
            <Link key={r.href} href={r.href}
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
          {health ? (
            <>
              <span>Clinic: <span className="text-fg-muted">{health.hospital}</span></span>
              <span className="flex items-center gap-1.5">
                AI model <Badge tone={health.llm.configured ? "success" : "warning"}>{health.llm.configured ? health.llm.model : "fallback mode"}</Badge>
              </span>
              <span className="flex items-center gap-1.5">
                HMS <Badge tone={health.hms.connected ? "success" : "danger"}>{health.hms.provider}</Badge>
              </span>
            </>
          ) : (
            <Badge tone="danger">API offline</Badge>
          )}
        </div>
      </main>
    </div>
  );
}