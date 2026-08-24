"use client";

import Link from "next/link";
import { useState } from "react";
import { Alert, Avatar, Badge, Card, EmptyState, Icons, PriorityBadge, StatusBadge } from "@/components/ui";
import type { CaseListItem } from "@/lib/api/types";
import { cn, formatDate } from "@/lib/utils";
import { groupPatients, type PatientGroup } from "@/features/clinic/derive";

export function PatientsDirectory({ cases }: { cases: CaseListItem[] }) {
  const groups = groupPatients(cases);
  if (groups.length === 0) {
    return <EmptyState icon={<Icons.user size={20} />} title="No patients yet" />;
  }
  return (
    <div className="space-y-4">
      <Alert tone="info">
        There is no patient table in this proof of concept. Patients are derived from cases: by hospital record number when linked, otherwise by the name the patient gave. Unnamed cases are never merged.
      </Alert>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {groups.map((g) => <PatientCard key={g.key} group={g} />)}
      </div>
    </div>
  );
}

function PatientCard({ group }: { group: PatientGroup }) {
  const [open, setOpen] = useState(false);
  const latest = group.cases[0];
  return (
    <Card className="p-4">
      <div className="flex items-start gap-3">
        <Avatar name={group.name || "?"} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{group.name || <span className="text-fg-subtle">Unnamed patient</span>}</p>
          <p className="flex flex-wrap items-center gap-1.5 text-xs text-fg-subtle">
            {group.mrn ? <Badge tone="info" className="px-1.5 py-0 text-[10px]">{group.mrn}</Badge> : <span>No hospital record linked</span>}
            <span>· {group.cases.length} {group.cases.length === 1 ? "visit" : "visits"}</span>
          </p>
        </div>
        <StatusBadge status={latest.status} />
      </div>
      <p className="mt-3 truncate text-sm text-fg-muted" title={latest.chief_complaint ?? undefined}>{latest.chief_complaint ?? "No complaint recorded"}</p>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="mt-3 flex h-8 items-center gap-1 text-xs font-medium text-brand">
        <Icons.chevronDown size={14} className={cn("transition-transform", open && "rotate-180")} /> {open ? "Hide visits" : "Show visits"}
      </button>
      {open ? (
        <ul className="mt-2 divide-y divide-line border-t border-line">
          {group.cases.map((c) => (
            <li key={c.case_id}>
              <Link href={`/cases/${c.case_id}`} className="flex items-center justify-between gap-3 py-2.5 text-sm hover:text-brand">
                <span className="min-w-0">
                  <span className="block truncate">{c.chief_complaint ?? "Intake"}</span>
                  <span className="text-xs text-fg-subtle">{formatDate(c.created_at)} · {c.department_name ?? "not routed"}</span>
                </span>
                <span className="flex shrink-0 items-center gap-2"><PriorityBadge priority={c.priority} /><Icons.chevronRight size={14} className="text-fg-subtle" /></span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}