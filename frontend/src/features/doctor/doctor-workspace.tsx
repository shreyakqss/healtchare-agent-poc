"use client";

import Link from "next/link";
import { useState } from "react";
import { casesApi, type CaseListItem, type HospitalConfig, type Roster, type WeeklyHours } from "@/lib/api";
import { DoctorHours } from "@/features/scheduling/doctor-hours";
import { Alert, Avatar, Button, Icons, PriorityBadge, StatusBadge, useToast } from "@/components/ui";
import { DoctorCalendar } from "@/features/doctor/doctor-calendar";
import { resolveMe } from "@/features/doctor/use-doctor";
import { isMine } from "@/features/doctor/worklist";

export function DoctorWorkspace({ initialCases, initialConfig, initialRoster, initialHours, authenticatedHmsUsername }: {
  initialCases: CaseListItem[]; initialConfig: HospitalConfig | null; initialRoster: Roster | null; initialHours: WeeklyHours[];
  authenticatedHmsUsername: string | null;
}) {
  // The roster endpoint merges live hospital-system practitioners over the clinic config; if
  // it is unavailable, fall back to whatever doctors the config itself declares (usually none).
  const roster: Roster = initialRoster ?? {
    source: "config",
    doctors: (initialConfig?.doctors ?? []).map((d) => ({ ...d, specialty: null, working_days: d.working_days ?? [], username: d.username ?? null })),
  };
  const me = resolveMe(authenticatedHmsUsername, roster.doctors, initialConfig?.departments ?? []);
  const [cases, setCases] = useState(initialCases);
  const [refreshing, setRefreshing] = useState(false);
  const toast = useToast();

  if (!initialConfig) {
    return <Alert tone="danger" title="Clinic configuration unavailable">The API did not return a hospital configuration. Start the backend and reload.</Alert>;
  }
  if (!me) {
    return (
      <Alert tone="danger" title="Hospital identity is not linked">
        Ask an administrator to set your Keycloak <code>hms_username</code> attribute to your OpenEMR username.
      </Alert>
    );
  }

  const unscheduled = cases.filter((c) => isMine(c, me) && !c.appointment_start);

  async function refreshList() {
    setRefreshing(true);
    try {
      setCases(await casesApi.list());
    } catch {
      toast.push({ tone: "danger", message: "Could not refresh the worklist" });
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Avatar name={me.name} />
        <div className="min-w-0">
          <p className="text-sm font-semibold leading-5">{me.name}</p>
          <p className="text-xs text-fg-muted">{me.department_name}</p>
        </div>
        <p className="ml-auto hidden text-xs text-fg-subtle sm:block">Reviews, notes and releases are verified against your hospital-system login.</p>
      </div>

      <div className="flex flex-wrap items-start justify-between gap-3">
        {initialHours.length ? <DoctorHours hours={initialHours} /> : <span />}
        <Button variant="secondary" onClick={refreshList} loading={refreshing} icon={<Icons.refresh size={16} />}>
          Refresh
        </Button>
      </div>

      {unscheduled.length ? (
        <div>
          <h2 className="mb-2 text-base font-semibold">Awaiting a time</h2>
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
            {unscheduled.map((c) => (
              <li key={c.case_id}>
                <Link href={`/cases/${c.case_id}`} className="flex items-center gap-3 px-3 py-2 hover:bg-sunken">
                  <Avatar name={c.demographics.name || "Unnamed patient"} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{c.demographics.name || "Unnamed patient"}</p>
                    <p className="truncate text-xs text-fg-muted">{c.chief_complaint ?? "No chief complaint"}</p>
                  </div>
                  <PriorityBadge priority={c.priority} />
                  <StatusBadge status={c.status} />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div>
        <h2 className="mb-2 text-base font-semibold">Calendar</h2>
        <DoctorCalendar cases={cases} me={me} />
      </div>
    </div>
  );
}
