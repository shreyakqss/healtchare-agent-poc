"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { PastPatientItem } from "@/lib/api";
import { Avatar, EmptyState, Icons, Input, Segmented, Select, StatusBadge } from "@/components/ui";
import type { Me } from "@/features/doctor/use-doctor";

type Scope = "mine" | "clinic";
const RANGES = [
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
  { value: "365", label: "Last year" },
  { value: "all", label: "All time" },
] as const;
type Range = (typeof RANGES)[number]["value"];

const DATE = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });
const DAY_MS = 24 * 60 * 60 * 1000;

/** Patients with a visit that is over (services/past_patients), one row per patient, newest
 * first. The list is loaded once with the page; search, scope and date range filter it here. */
export function PastPatients({ patients, me, now }: { patients: PastPatientItem[]; me: Me; now: string }) {
  const [scope, setScope] = useState<Scope>("mine");
  const [range, setRange] = useState<Range>("90");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const since = range === "all" ? null : new Date(now).getTime() - Number(range) * DAY_MS;
    const out: PastPatientItem[] = [];
    for (const p of patients) {
      const visits = scope === "mine" ? p.visits.filter((v) => v.doctor_id === me.id) : p.visits;
      if (!visits.length) continue;
      if (since !== null && new Date(visits[0].visit_at).getTime() < since) continue;
      if (needle) {
        const text = [p.name, p.hms_patient_id, ...visits.flatMap((v) => [v.chief_complaint, v.doctor_name])]
          .filter(Boolean).join(" ").toLowerCase();
        if (!text.includes(needle)) continue;
      }
      out.push({ ...p, visits, visit_count: visits.length, last_visit_at: visits[0].visit_at });
    }
    return out;
  }, [patients, scope, range, query, me.id, now]);

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Icons.search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-subtle" />
          <Input
            value={query} onChange={(e) => setQuery(e.target.value)} className="pl-9"
            placeholder="Search name, MRN, complaint or doctor" aria-label="Search past patients"
          />
        </div>
        <Segmented<Scope>
          label="Whose patients" value={scope} onChange={setScope}
          options={[{ value: "mine", label: "My patients" }, { value: "clinic", label: "Whole clinic" }]}
        />
        <Select value={range} onChange={(e) => setRange(e.target.value as Range)} aria-label="Last visit within" className="sm:w-40">
          {RANGES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
        </Select>
      </div>

      {shown.length ? (
        <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
          {shown.map((p) => {
            const expanded = open === p.patient_key;
            const last = p.visits[0];
            return (
              <li key={p.patient_key}>
                <button
                  type="button" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : p.patient_key)}
                  className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-sunken"
                >
                  <Avatar name={p.name || "Unnamed patient"} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {p.name || "Unnamed patient"}
                      <span className="ml-2 text-xs font-normal text-fg-muted">
                        {[p.age ? `${p.age} y` : null, p.sex, p.hms_patient_id ? `MRN ${p.hms_patient_id}` : null].filter(Boolean).join(" · ")}
                      </span>
                    </p>
                    <p className="truncate text-xs text-fg-muted">{last.chief_complaint ?? "No chief complaint"}</p>
                  </div>
                  <div className="hidden text-right text-xs text-fg-muted sm:block">
                    <p>Last visit {DATE.format(new Date(p.last_visit_at))}</p>
                    <p>{p.visit_count} {p.visit_count === 1 ? "visit" : "visits"}</p>
                  </div>
                  <Icons.chevronDown size={16} className={expanded ? "shrink-0 rotate-180 text-fg-subtle" : "shrink-0 text-fg-subtle"} />
                </button>
                {expanded ? (
                  <ul className="space-y-1 border-t border-line bg-sunken px-3 py-2">
                    {p.visits.map((v) => (
                      <li key={v.case_id}>
                        <Link href={`/cases/${v.case_id}`} className="flex items-center gap-3 rounded-md px-2 py-1.5 hover:bg-surface">
                          <span className="w-24 shrink-0 text-xs text-fg-muted">{DATE.format(new Date(v.visit_at))}</span>
                          <span className="min-w-0 flex-1 truncate text-sm">{v.chief_complaint ?? "No chief complaint"}</span>
                          <span className="hidden truncate text-xs text-fg-muted sm:inline">{v.doctor_name ?? v.department_name}</span>
                          <StatusBadge status={v.status} />
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="rounded-lg border border-line bg-surface">
          <EmptyState
            icon={<Icons.user size={20} />}
            title={patients.length ? "No past patients match" : "No past patients yet"}
            description={patients.length ? "Try another search, “Whole clinic”, or a longer date range." : "Patients appear here once their visit is over."}
          />
        </div>
      )}
    </div>
  );
}
