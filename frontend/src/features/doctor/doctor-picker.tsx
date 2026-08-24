"use client";

import type { HospitalConfig } from "@/lib/api";
import { Avatar, Card, CardBody, CardHeader, Icons } from "@/components/ui";

export function DoctorPicker({ config, onPick }: { config: HospitalConfig; onPick: (id: string) => void }) {
  return (
    <div className="mx-auto max-w-2xl">
      <Card>
        <CardHeader title="Who is working today?" description="Pick your name from the roster. Every action you take is audited under it." />
        <CardBody className="space-y-5">
          {config.departments.map((dep) => {
            const docs = config.doctors.filter((d) => d.department_id === dep.id);
            if (!docs.length) return null;
            return (
              <div key={dep.id}>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-fg-subtle">{dep.name}</p>
                <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                  {docs.map((d) => (
                    <li key={d.id}>
                      <button
                        type="button"
                        onClick={() => onPick(d.id)}
                        className="flex h-14 w-full items-center gap-3 rounded-md border border-line bg-surface px-3 text-left transition-colors hover:border-brand-ring hover:bg-brand-soft/40"
                      >
                        <Avatar name={d.name} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">{d.name}</span>
                          <span className="block text-xs text-fg-muted">{(d.working_days ?? []).map((w) => w[0].toUpperCase() + w.slice(1)).join(" · ") || "No roster"}</span>
                        </span>
                        <Icons.chevronRight size={16} className="text-fg-subtle" />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
          <p className="text-xs text-fg-subtle">There is no sign-in in this proof of concept. Selecting a name is the whole of it.</p>
        </CardBody>
      </Card>
    </div>
  );
}