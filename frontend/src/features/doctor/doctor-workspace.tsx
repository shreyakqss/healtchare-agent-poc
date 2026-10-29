"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { casesApi, type CaseListItem, type HospitalConfig, type PastPatientItem, type Roster, type WeeklyHours } from "@/lib/api";
import { DoctorHours } from "@/features/scheduling/doctor-hours";
import { Alert, Avatar, Button, EmptyState, Icons, PriorityBadge, StatusBadge, Tabs, useToast } from "@/components/ui";
import { DoctorCalendar } from "@/features/doctor/doctor-calendar";
import { PastPatients } from "@/features/doctor/past-patients";
import { resolveMe } from "@/features/doctor/use-doctor";
import { isMine } from "@/features/doctor/worklist";

type TabId = "today" | "action" | "upcoming" | "past" | "calendar";
const CLOSED = new Set(["COMPLETED", "REJECTED"]);
const TIME = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
const DAY_TIME = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

/** List first, calendar second, as clinic apps do: today's patients, what needs the doctor,
 * what's coming, and a searchable "Past patients" list. `now` comes from the server render so
 * the day split is the same on both sides. */
export function DoctorWorkspace({ initialCases, initialPast, initialConfig, initialRoster, initialHours, authenticatedHmsUsername, now }: {
  initialCases: CaseListItem[]; initialPast: PastPatientItem[]; initialConfig: HospitalConfig | null; initialRoster: Roster | null;
  initialHours: WeeklyHours[]; authenticatedHmsUsername: string | null; now: string;
}) {
  // The roster endpoint merges live hospital-system practitioners over the clinic config; if
  // it is unavailable, fall back to whatever doctors the config itself declares (usually none).
  const roster: Roster = initialRoster ?? {
    source: "config",
    doctors: (initialConfig?.doctors ?? []).map((d) => ({ ...d, specialty: null, working_days: d.working_days ?? [], username: d.username ?? null })),
  };
  const me = resolveMe(authenticatedHmsUsername, roster.doctors, initialConfig?.departments ?? []);
  const [cases, setCases] = useState(initialCases);
  const [past, setPast] = useState(initialPast);
  const [tab, setTab] = useState<TabId>("today");
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

  const nowMs = new Date(now).getTime();
  const endOfToday = new Date(now);
  endOfToday.setHours(23, 59, 59, 999);
  const startOfToday = new Date(now);
  startOfToday.setHours(0, 0, 0, 0);
  const at = (c: CaseListItem) => (c.appointment_start ? new Date(c.appointment_start).getTime() : null);
  const byTime = (a: CaseListItem, b: CaseListItem) => (at(a) ?? 0) - (at(b) ?? 0);

  const mine = cases.filter((c) => isMine(c, me));
  // Red-flag cases are never booked (the patient was told to call an ambulance): always on top, oldest first.
  const emergencies = mine.filter((c) => c.emergency && c.status === "NEEDS_REVIEW")
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
  const toReview = mine.filter((c) => !c.emergency && c.status === "NEEDS_REVIEW").sort(byTime);
  const unscheduled = mine.filter((c) => !c.appointment_start && !c.emergency && !CLOSED.has(c.status));
  const today = mine.filter((c) => { const t = at(c); return t !== null && t >= startOfToday.getTime() && t <= endOfToday.getTime(); }).sort(byTime);
  const upcoming = mine.filter((c) => { const t = at(c); return t !== null && t > endOfToday.getTime() && !CLOSED.has(c.status); }).sort(byTime);
  const actionCount = emergencies.length + toReview.length + unscheduled.length;

  async function refreshList() {
    setRefreshing(true);
    try {
      const [list, pastList] = await Promise.all([casesApi.list(), casesApi.pastPatients()]);
      setCases(list);
      setPast(pastList);
    } catch {
      toast.push({ tone: "danger", message: "Could not refresh the worklist" });
    } finally {
      setRefreshing(false);
    }
  }

  const tabs: Array<{ id: TabId; label: string; count?: number }> = [
    { id: "today", label: "Today", count: today.length },
    { id: "action", label: "Needs action", count: actionCount },
    { id: "upcoming", label: "Upcoming", count: upcoming.length },
    { id: "past", label: "Past patients" },
    { id: "calendar", label: "Calendar" },
  ];

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

      {emergencies.length && tab !== "action" ? (
        <button type="button" onClick={() => setTab("action")}
          className="flex w-full items-center gap-2 rounded-lg border-2 border-danger bg-danger-soft px-3 py-2 text-left text-sm font-medium text-danger">
          <Icons.alert size={16} /> {emergencies.length} emergency {emergencies.length === 1 ? "case" : "cases"}: patient told to call an ambulance
          <Icons.chevronRight size={16} className="ml-auto" />
        </button>
      ) : null}

      <div className="overflow-x-auto">
        <Tabs idPrefix="doctor" tabs={tabs} value={tab} onChange={setTab} className="min-w-max sm:min-w-0" />
      </div>

      <div id={`doctor-panel-${tab}`} role="tabpanel" aria-labelledby={`doctor-tab-${tab}`} className="space-y-4">
        {tab === "today" ? (
          <CaseList cases={today} empty="No appointments today." when={(c) => TIME.format(new Date(c.appointment_start!))}
            note={(c) => (at(c)! < nowMs && !CLOSED.has(c.status) ? "Time passed" : null)} />
        ) : null}

        {tab === "action" ? (
          actionCount ? (
            <>
              {emergencies.length ? (
                <Section title={`Emergency: patient told to call an ambulance (${emergencies.length})`} danger>
                  <CaseList cases={emergencies} danger when={(c) => TIME.format(new Date(c.created_at))} />
                </Section>
              ) : null}
              {toReview.length ? (
                <Section title={`Waiting for your review (${toReview.length})`}>
                  <CaseList cases={toReview} when={(c) => (c.appointment_start ? DAY_TIME.format(new Date(c.appointment_start)) : "Not booked")} />
                </Section>
              ) : null}
              {unscheduled.length ? (
                <Section title={`Awaiting a time (${unscheduled.length})`}>
                  <CaseList cases={unscheduled} />
                </Section>
              ) : null}
            </>
          ) : <Empty text="Nothing needs you right now." />
        ) : null}

        {tab === "upcoming" ? (
          <CaseList cases={upcoming} empty="No upcoming appointments." when={(c) => DAY_TIME.format(new Date(c.appointment_start!))} />
        ) : null}

        {tab === "past" ? <PastPatients patients={past} now={now} /> : null}

        {tab === "calendar" ? <DoctorCalendar cases={cases} me={me} /> : null}
      </div>
    </div>
  );
}

function Section({ title, danger, children }: { title: string; danger?: boolean; children: ReactNode }) {
  return (
    <div>
      <h2 className={danger ? "mb-2 flex items-center gap-1.5 text-base font-semibold text-danger" : "mb-2 text-base font-semibold"}>
        {danger ? <Icons.alert size={16} /> : null} {title}
      </h2>
      {children}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface">
      <EmptyState icon={<Icons.calendar size={20} />} title={text} />
    </div>
  );
}

function CaseList({ cases, empty, when, note, danger }: {
  cases: CaseListItem[]; empty?: string; when?: (c: CaseListItem) => string; note?: (c: CaseListItem) => string | null; danger?: boolean;
}) {
  if (!cases.length) return empty ? <Empty text={empty} /> : null;
  return (
    <ul className={danger ? "divide-y divide-line rounded-lg border-2 border-danger bg-danger-soft" : "divide-y divide-line rounded-lg border border-line bg-surface"}>
      {cases.map((c) => (
        <li key={c.case_id}>
          <Link href={`/cases/${c.case_id}`} className="flex items-center gap-3 px-3 py-2.5 hover:bg-sunken">
            {when ? <span className="w-28 shrink-0 text-sm font-medium tabular">{when(c)}</span> : null}
            <Avatar name={c.demographics.name || "Unnamed patient"} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{c.demographics.name || "Unnamed patient"}</p>
              <p className="truncate text-xs text-fg-muted">{c.chief_complaint ?? "No chief complaint"}</p>
            </div>
            {note?.(c) ? <span className="hidden text-xs text-fg-subtle sm:inline">{note(c)}</span> : null}
            {danger ? null : <PriorityBadge priority={c.priority} />}
            <StatusBadge status={c.status} />
          </Link>
        </li>
      ))}
    </ul>
  );
}
