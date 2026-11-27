"use client";

import { useMemo, useState } from "react";
import type { AdminPatientItem } from "@/lib/api";
import { PageHeader } from "@/components/layout/page-header";
import { Avatar, EmptyState, Icons, Input, Select, StatusBadge } from "@/components/ui";

const DATE_TIME = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
const DATE = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });

/** The clinic's patients for the administrator: who, which department and doctor, when, and
 * where each visit stands. Administrative only - no clinical detail, and rows never open a case. */
export function PatientsDirectory({ patients }: { patients: AdminPatientItem[] }) {
  const [query, setQuery] = useState("");
  const [department, setDepartment] = useState("all");
  const [open, setOpen] = useState<string | null>(null);

  const departments = useMemo(
    () => [...new Set(patients.flatMap((p) => p.visits.map((v) => v.department_name)).filter((d): d is string => Boolean(d)))].sort(),
    [patients],
  );
  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return patients.filter((p) =>
      (department === "all" || p.visits.some((v) => v.department_name === department))
      && (!needle || [p.name, p.hms_patient_id, ...p.visits.map((v) => v.doctor_name)].filter(Boolean).join(" ").toLowerCase().includes(needle)));
  }, [patients, query, department]);

  return (
    <div className="space-y-4">
      <PageHeader title="Patients" description="Everyone registered at your clinic, with their department, doctor and appointments. Clinical details stay with the treating doctor." />

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Icons.search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-subtle" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} className="pl-9" placeholder="Search name, MRN or doctor" aria-label="Search patients" />
        </div>
        <Select value={department} onChange={(e) => setDepartment(e.target.value)} aria-label="Department" className="sm:w-52">
          <option value="all">All departments</option>
          {departments.map((d) => <option key={d} value={d}>{d}</option>)}
        </Select>
        <span className="text-sm text-fg-muted">{shown.length} of {patients.length}</span>
      </div>

      {shown.length ? (
        <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
          {shown.map((p) => {
            const latest = p.visits[0];
            const expanded = open === p.hms_patient_id;
            return (
              <li key={p.hms_patient_id}>
                <button type="button" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : p.hms_patient_id)}
                  className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-sunken">
                  <Avatar name={p.name || "Unnamed patient"} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {p.name || "Unnamed patient"}
                      <span className="ml-2 text-xs font-normal text-fg-muted">
                        {[p.age ? `${p.age} y` : null, p.sex, `MRN ${p.hms_patient_id}`].filter(Boolean).join(" · ")}
                      </span>
                    </p>
                    <p className="truncate text-xs text-fg-muted">
                      {[latest.department_name, latest.doctor_name].filter(Boolean).join(" · ") || "Not routed yet"}
                    </p>
                  </div>
                  <div className="hidden text-right text-xs text-fg-muted sm:block">
                    <p>{latest.appointment_start ? DATE_TIME.format(new Date(latest.appointment_start)) : "No appointment"}</p>
                    <p>{p.visit_count} {p.visit_count === 1 ? "visit" : "visits"}</p>
                  </div>
                  <StatusBadge status={latest.status} />
                  <Icons.chevronDown size={16} className={expanded ? "shrink-0 rotate-180 text-fg-subtle" : "shrink-0 text-fg-subtle"} />
                </button>
                {expanded ? (
                  <ul className="space-y-1 border-t border-line bg-sunken px-3 py-2">
                    {p.visits.map((v, i) => (
                      <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md px-2 py-1.5 text-sm">
                        <span className="w-44 shrink-0 text-xs text-fg-muted">
                          {v.appointment_start ? DATE_TIME.format(new Date(v.appointment_start)) : `Started ${DATE.format(new Date(v.created_at))}`}
                        </span>
                        <span className="min-w-0 flex-1 truncate">{[v.department_name, v.doctor_name].filter(Boolean).join(" · ") || "Not routed yet"}</span>
                        <span className="text-xs text-fg-subtle">{v.appointment_booked ? "Booked" : v.appointment_start ? "Not confirmed" : ""}</span>
                        <StatusBadge status={v.status} />
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
          <EmptyState icon={<Icons.user size={20} />} title={patients.length ? "No patients match" : "No patients yet"}
            description={patients.length ? "Try another search or department." : "Patients appear here once they register through intake."} />
        </div>
      )}
    </div>
  );
}
