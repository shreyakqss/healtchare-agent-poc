"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ApiError,
  api,
  type CaseListItem,
  type HospitalConfig,
} from "@/lib/api";
import { DEMO_NOTICE } from "@/lib/demo";
import {
  BarList,
  Banner,
  Button,
  DemoBanner,
  Donut,
  Dot,
  Empty,
  Metric,
  Panel,
  PriorityTag,
  Tag,
  caseRef,
  icons,
  since,
  type Slice,
  type Tone,
} from "@/lib/ui";

/**
 * The staff surface: a sidebar and six screens over one list of cases.
 *
 * | Section | What it answers |
 * |---|---|
 * | Overview | how the clinic is doing right now |
 * | Live queue | every case, filterable |
 * | Needs review | the cases actually blocked on a clinician |
 * | Patients | everyone who has been through, and where they got to |
 * | Doctors | the roster and what each one is carrying |
 * | Completed | what has been finished |
 *
 * There is one fetch and one `cases` array behind all of them — the sections
 * are views over it, not separate loads, so switching is instant and the
 * numbers in the sidebar always agree with the tables. The doctor roster is
 * the one extra input, and it comes from the active clinic's config.
 *
 * This is the clinic-wide view. The single doctor's own worklist, and the
 * place a consultation is actually recorded, is `/doctor`.
 */

/** Lifecycle statuses collapsed into the five stages staff think in. */
const STAGES = [
  { key: "intake", label: "Intake", statuses: ["CREATED", "INGESTING"], tone: "neutral" },
  { key: "prescreen", label: "Pre-screening", statuses: ["ANALYZING"], tone: "info" },
  { key: "review", label: "Review", statuses: ["NEEDS_REVIEW"], tone: "med" },
  { key: "consult", label: "Consultation", statuses: ["APPROVED"], tone: "accent" },
  { key: "done", label: "Completed", statuses: ["COMPLETED"], tone: "low" },
] as const;

const stageFor = (status: string) =>
  STAGES.find((stage) => (stage.statuses as readonly string[]).includes(status));

type Section = "overview" | "queue" | "review" | "patients" | "doctors" | "done";

const SECTIONS: {
  key: Section;
  label: string;
  hint: string;
  Icon: (typeof icons)["grid"];
}[] = [
  { key: "overview", label: "Overview", hint: "Clinic at a glance", Icon: icons.pulse },
  { key: "queue", label: "Live queue", hint: "Every open case", Icon: icons.grid },
  { key: "review", label: "Needs review", hint: "Waiting on a clinician", Icon: icons.alert },
  { key: "patients", label: "Patients", hint: "Everyone on record", Icon: icons.users },
  { key: "doctors", label: "Doctors", hint: "Roster and workload", Icon: icons.stethoscope },
  { key: "done", label: "Completed", hint: "Finished visits", Icon: icons.check },
];

/** Elapsed wall-clock from case creation to its last recorded event. */
function responseMs(item: CaseListItem) {
  if (!item.updated_at) return null;
  return new Date(item.updated_at).getTime() - new Date(item.created_at).getTime();
}

function patientLabel(item: CaseListItem) {
  const {
    name,
    fixture_id: id,
    age,
    sex,
    simulated,
  } = item.demographics as Record<string, unknown>;
  const descriptor = [age && `${age}`, sex].filter(Boolean).join(" ");
  return {
    // `name` is what intake collected; `fixture_id` is what a seeded or
    // simulated case was labelled with before anyone said anything.
    name: (name as string) ?? (id as string) ?? "Synthetic patient",
    descriptor: descriptor || "demographics not recorded",
    // Set by the simulation API when it opens a case. Nothing branches on it
    // beyond this label — a simulated case is an ordinary case.
    simulated: simulated === true,
  };
}

export default function DashboardView({
  initialCases,
  doctors,
  departments,
  demo,
}: {
  initialCases: CaseListItem[];
  doctors: HospitalConfig["doctors"];
  departments: HospitalConfig["departments"];
  /** True when the backend was unreachable and these are preview patients. */
  demo: boolean;
}) {
  const [section, setSection] = useState<Section>("overview");
  const [cases, setCases] = useState(initialCases);
  const [error, setError] = useState<string | null>(null);
  // Clock read once per mount and again on refresh, so relative times are
  // stable across a render rather than moving under the table.
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<string | null>(null);

  async function refresh() {
    setBusy(true);
    try {
      setCases(await api.listCases());
      setNow(Date.now());
      setError(null);
    } catch (err) {
      // In preview mode this is expected — keep the invented cases on screen
      // rather than blanking the table with an error.
      if (!demo) setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const count = (statuses: readonly string[]) =>
    cases.filter((c) => statuses.includes(c.status)).length;

  const needsReview = cases.filter((c) => c.status === "NEEDS_REVIEW");
  const completed = cases.filter((c) =>
    ["COMPLETED", "REJECTED"].includes(c.status),
  );
  const openCases = cases.filter(
    (c) => !["COMPLETED", "REJECTED"].includes(c.status),
  );

  const badge = (key: Section) => {
    switch (key) {
      case "review":
        return needsReview.length;
      case "done":
        return completed.length;
      case "queue":
        return openCases.length;
      case "patients":
        return cases.length;
      case "doctors":
        return doctors.length;
      default:
        return 0;
    }
  };

  return (
    <div className="grid items-start gap-5 lg:grid-cols-[15rem_minmax(0,1fr)]">
      {/* --- sidebar ------------------------------------------------------ */}
      <aside className="flex flex-col gap-4 lg:sticky lg:top-20">
        <div className="rounded-md border border-line bg-surface/80 p-4">
          <p className="eyebrow">Hospital staff</p>
          <p className="mt-1 text-sm font-semibold tracking-tight text-text">
            Patient queue
          </p>
          <p className="mt-1.5 text-[11px] leading-4 text-faint">
            {cases.length} case{cases.length === 1 ? "" : "s"} in the clinic ·{" "}
            {openCases.length} open
          </p>
        </div>

        <nav className="rounded-md border border-line bg-surface/80 p-1.5">
          <ul className="space-y-0.5">
            {SECTIONS.map(({ key, label, hint, Icon }) => {
              const active = section === key;
              const value = badge(key);
              return (
                <li key={key}>
                  <button
                    onClick={() => {
                      setSection(key);
                      setFilter(null);
                    }}
                    aria-current={active ? "page" : undefined}
                    className={`flex w-full items-center gap-3 rounded px-3 py-2.5 text-left transition-colors ${
                      active
                        ? "bg-accent/10 text-text"
                        : "text-dim hover:bg-raised/60 hover:text-text"
                    }`}
                  >
                    <Icon
                      className={`shrink-0 text-[17px] ${
                        active ? "text-accent" : "text-faint"
                      }`}
                    />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">
                        {label}
                      </span>
                      <span className="block truncate text-[11px] text-faint">
                        {hint}
                      </span>
                    </span>
                    {value > 0 && (
                      <span
                        className={`nums ml-auto rounded px-1.5 py-0.5 text-[10px] ${
                          key === "review"
                            ? "bg-med/15 text-med"
                            : "bg-raised text-dim"
                        }`}
                      >
                        {value}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <Button
          onClick={() => void refresh()}
          disabled={busy}
          className="justify-center"
        >
          <icons.refresh className={busy ? "animate-spin text-[15px]" : "text-[15px]"} />
          {busy ? "Refreshing" : "Refresh"}
        </Button>
      </aside>

      {/* --- screen ------------------------------------------------------- */}
      <div className="min-w-0 space-y-5">
        {demo && <DemoBanner>{DEMO_NOTICE}</DemoBanner>}
        {error && <Banner tone="error">{error}</Banner>}

        {section === "overview" && (
          <Overview cases={cases} count={count} filter={filter} onFilter={setFilter} />
        )}

        {section === "queue" && (
          <CaseTable
            title="Live queue"
            eyebrow="All cases"
            cases={cases}
            filter={filter}
            onFilter={setFilter}
            now={now}
            emptyAll
          />
        )}

        {section === "review" && (
          <>
            <Panel eyebrow="Blocked on a clinician" title="Needs review">
              <p className="text-sm leading-6 text-dim">
                Nothing downstream of these cases can happen until someone
                approves, edits or rejects them — consultation notes and the
                final summary are both refused by the API until a review
                exists. Open a case to review it.
              </p>
            </Panel>
            <CaseTable
              title={`${needsReview.length} waiting`}
              eyebrow="Review queue"
              cases={needsReview}
              filter={filter}
              onFilter={setFilter}
              now={now}
              empty="Nothing is waiting on a clinician right now."
            />
          </>
        )}

        {section === "patients" && <Patients cases={cases} now={now} />}

        {section === "doctors" && (
          <Doctors cases={cases} doctors={doctors} departments={departments} />
        )}

        {section === "done" && (
          <CaseTable
            title={`${completed.length} finished`}
            eyebrow="Completed"
            cases={completed}
            filter={filter}
            onFilter={setFilter}
            now={now}
            empty="No visits have been completed yet."
          />
        )}
      </div>
    </div>
  );
}

/* --- overview -------------------------------------------------------------- */

function Overview({
  cases,
  count,
  filter,
  onFilter,
}: {
  cases: CaseListItem[];
  count: (statuses: readonly string[]) => number;
  filter: string | null;
  onFilter: (key: string | null) => void;
}) {
  const responses = cases.map(responseMs).filter((ms): ms is number => ms !== null);
  const avgResponse = responses.length
    ? responses.reduce((a, b) => a + b, 0) / responses.length / 1000
    : null;

  const priorityMix: Slice[] = [
    { label: "High", value: cases.filter((c) => c.priority === "high").length, tone: "high" },
    { label: "Medium", value: cases.filter((c) => c.priority === "medium").length, tone: "med" },
    { label: "Low", value: cases.filter((c) => c.priority === "low").length, tone: "low" },
  ];

  const departments: Slice[] = Object.entries(
    cases.reduce<Record<string, number>>((acc, item) => {
      const key = item.department ?? "Unrouted";
      acc[key] = (acc[key] ?? 0) + 1;
      return acc;
    }, {}),
  )
    .map(([label, value]) => ({ label, value, tone: "info" as Tone }))
    .sort((a, b) => b.value - a.value);

  return (
    <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <Metric
          label="Incoming"
          value={count(["CREATED", "INGESTING"])}
          hint="awaiting pre-screening"
          icon={<icons.users />}
        />
        <Metric
          label="AI processing"
          value={count(["ANALYZING"])}
          hint="agents executing"
          tone="info"
          icon={<icons.pulse />}
        />
        <Metric
          label="Needs review"
          value={count(["NEEDS_REVIEW"])}
          hint="blocked on a clinician"
          tone="med"
          icon={<icons.alert />}
        />
        <Metric
          label="In consultation"
          value={count(["APPROVED"])}
          hint="approved, notes pending"
          tone="accent"
          icon={<icons.stethoscope />}
        />
        <Metric
          label="Completed"
          value={count(["COMPLETED"])}
          hint="summary released"
          tone="low"
          icon={<icons.check />}
        />
        <Metric
          label="Avg response"
          value={avgResponse === null ? "—" : `${avgResponse.toFixed(1)}s`}
          hint="case created → last event"
          icon={<icons.clock />}
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <Panel eyebrow="Triage" title="Priority distribution">
          {cases.length ? (
            <Donut data={priorityMix} caption="cases" />
          ) : (
            <Empty>No cases yet.</Empty>
          )}
        </Panel>

        <Panel eyebrow="Routing" title="Department distribution">
          <BarList data={departments} empty="Nothing routed yet." />
        </Panel>
      </div>

      <Panel eyebrow="Throughput" title="Case flow">
        <ol className="space-y-1">
          {STAGES.map((stage, index) => {
            const value = count(stage.statuses);
            const width = cases.length ? (value / cases.length) * 100 : 0;
            return (
              <li key={stage.key}>
                <button
                  onClick={() => onFilter(filter === stage.key ? null : stage.key)}
                  className={`flex w-full items-center gap-3 rounded px-2 py-1.5 text-left transition-colors hover:bg-raised ${
                    filter === stage.key ? "bg-raised" : ""
                  }`}
                >
                  <Dot tone={stage.tone} live={stage.key === "prescreen" && value > 0} />
                  <span className="w-28 shrink-0 text-sm text-dim">{stage.label}</span>
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-line-soft">
                    <span
                      className="block h-full rounded-full transition-[width] duration-500"
                      style={{
                        width: `${width}%`,
                        background: `var(--color-${stage.tone === "neutral" ? "faint" : stage.tone})`,
                      }}
                    />
                  </span>
                  <span className="nums w-6 text-right text-sm font-medium">{value}</span>
                </button>
                {index < STAGES.length - 1 && (
                  <span className="ml-[0.72rem] block h-2 w-px bg-line" />
                )}
              </li>
            );
          })}
        </ol>
      </Panel>
    </>
  );
}

/* --- patients -------------------------------------------------------------- */

/**
 * Everyone the clinic has on record, one row per person rather than per case.
 *
 * Cases are grouped by patient name because that is the only identifier there
 * is — the backend has no patient table, so two visits by the same person are
 * only the same person if they gave the same name. Anyone who did not give a
 * name stays as their own row rather than being merged into a single
 * "unknown" patient, which would invent a person who does not exist.
 */
function Patients({ cases, now }: { cases: CaseListItem[]; now: number }) {
  const groups = new Map<string, { label: string; descriptor: string; items: CaseListItem[] }>();
  for (const item of cases) {
    const patient = patientLabel(item);
    // Fall back to the case id so unnamed patients are not merged together.
    const key = patient.name === "Synthetic patient" ? item.case_id : patient.name;
    const existing = groups.get(key);
    if (existing) existing.items.push(item);
    else
      groups.set(key, {
        label: patient.name,
        descriptor: patient.descriptor,
        items: [item],
      });
  }
  const rows = [...groups.values()].sort(
    (a, b) => b.items.length - a.items.length || a.label.localeCompare(b.label),
  );

  return (
    <Panel eyebrow="Everyone on record" title={`${rows.length} patients`} bodyClassName="">
      {rows.length === 0 ? (
        <div className="p-5">
          <Empty>No patients yet.</Empty>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[48rem] text-sm">
            <thead>
              <tr className="border-b border-line-soft text-left">
                {["Patient", "Visits", "Latest reason", "Latest stage", "Last seen", ""].map(
                  (heading) => (
                    <th key={heading} className="eyebrow px-4 py-2.5 font-semibold">
                      {heading}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const latest = [...row.items].sort((a, b) =>
                  b.created_at.localeCompare(a.created_at),
                )[0];
                const stage = stageFor(latest.status);
                return (
                  <tr
                    key={row.label + latest.case_id}
                    className="group border-b border-line-soft/60 last:border-0 transition-colors hover:bg-raised/50"
                  >
                    <td className="px-4 py-3">
                      <p className="text-xs text-text">{row.label}</p>
                      <p className="text-[11px] text-faint">{row.descriptor}</p>
                    </td>
                    <td className="nums px-4 py-3 text-dim">{row.items.length}</td>
                    <td className="max-w-[20rem] truncate px-4 py-3 text-dim">
                      {latest.chief_complaint ?? (
                        <span className="text-faint">Not recorded</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {stage ? (
                        <Tag tone={stage.tone}>{stage.label}</Tag>
                      ) : (
                        <Tag tone="high">{latest.status}</Tag>
                      )}
                    </td>
                    <td className="nums px-4 py-3 text-faint" suppressHydrationWarning>
                      {since(latest.created_at, now)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        href={`/cases/${latest.case_id}`}
                        className="inline-flex items-center gap-1 text-xs text-faint transition-colors group-hover:text-accent"
                      >
                        Latest case
                        <icons.chevron className="text-[14px]" />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

/* --- doctors --------------------------------------------------------------- */

/**
 * The roster, joined to what each doctor is currently carrying.
 *
 * The join is on `doctor_name` because that is what the case list carries; a
 * doctor renamed in the YAML after a case was routed will read as unassigned
 * until that case is re-routed, which is honest rather than hidden.
 */
function Doctors({
  cases,
  doctors,
  departments,
}: {
  cases: CaseListItem[];
  doctors: HospitalConfig["doctors"];
  departments: HospitalConfig["departments"];
}) {
  const routed = new Set(doctors.map((d) => d.name));
  const unassigned = cases.filter(
    (c) => !c.doctor_name || !routed.has(c.doctor_name),
  );

  return (
    <>
      <Panel eyebrow="Roster" title={`${doctors.length} doctors`} bodyClassName="">
        {doctors.length === 0 ? (
          <div className="p-5">
            <Empty>
              No doctors configured. Add them under{" "}
              <Link href="/hospital" className="text-accent underline underline-offset-2">
                Configuration
              </Link>
              .
            </Empty>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[52rem] text-sm">
              <thead>
                <tr className="border-b border-line-soft text-left">
                  {[
                    "Doctor",
                    "Department",
                    "Awaiting review",
                    "To consult",
                    "Completed",
                    "Total",
                    "",
                  ].map((heading) => (
                    <th key={heading} className="eyebrow px-4 py-2.5 font-semibold">
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {doctors.map((doctor) => {
                  const theirs = cases.filter((c) => c.doctor_name === doctor.name);
                  const dept = departments.find((d) => d.id === doctor.department_id);
                  const byStatus = (status: string) =>
                    theirs.filter((c) => c.status === status).length;
                  const review = byStatus("NEEDS_REVIEW");
                  return (
                    <tr
                      key={doctor.id}
                      className="group border-b border-line-soft/60 last:border-0 transition-colors hover:bg-raised/50"
                    >
                      <td className="px-4 py-3">
                        <p className="flex items-center gap-2 text-xs text-text">
                          <span className="grid size-6 place-items-center rounded-full bg-accent/12 text-accent">
                            <icons.stethoscope className="text-[12px]" />
                          </span>
                          {doctor.name}
                        </p>
                        <p className="mt-0.5 font-mono text-[10px] text-faint">
                          {doctor.id}
                        </p>
                      </td>
                      <td className="px-4 py-3 text-dim">
                        {dept?.name ?? doctor.department_id}
                      </td>
                      <td className="px-4 py-3">
                        {review > 0 ? (
                          <Tag tone="med">
                            <Dot tone="med" live />
                            {review}
                          </Tag>
                        ) : (
                          <span className="nums text-faint">0</span>
                        )}
                      </td>
                      <td className="nums px-4 py-3 text-dim">{byStatus("APPROVED")}</td>
                      <td className="nums px-4 py-3 text-dim">{byStatus("COMPLETED")}</td>
                      <td className="nums px-4 py-3 font-medium">{theirs.length}</td>
                      <td className="px-4 py-3 text-right">
                        <Link
                          href="/doctor"
                          className="inline-flex items-center gap-1 text-xs text-faint transition-colors group-hover:text-accent"
                        >
                          Worklist
                          <icons.chevron className="text-[14px]" />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {unassigned.length > 0 && (
        <Panel eyebrow="Not on the roster" title={`${unassigned.length} unassigned cases`}>
          <p className="text-sm leading-6 text-dim">
            These cases have no doctor, or name one who is not in the active
            clinic&apos;s configuration. They will not appear on anyone&apos;s
            worklist until they are routed to a configured doctor.
          </p>
          <ul className="mt-3 flex flex-wrap gap-1.5">
            {unassigned.map((item) => (
              <li key={item.case_id}>
                <Link
                  href={`/cases/${item.case_id}`}
                  className="inline-flex items-center gap-1.5 rounded border border-line px-2 py-1 font-mono text-[11px] text-dim transition-colors hover:border-accent/50 hover:text-accent"
                >
                  {caseRef(item.case_id)}
                  {item.doctor_name && (
                    <span className="text-faint">· {item.doctor_name}</span>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </>
  );
}

/* --- case table ------------------------------------------------------------ */

function CaseTable({
  title,
  eyebrow,
  cases,
  filter,
  onFilter,
  now,
  empty,
  emptyAll = false,
}: {
  title: string;
  eyebrow: string;
  cases: CaseListItem[];
  filter: string | null;
  onFilter: (key: string | null) => void;
  now: number;
  empty?: string;
  /** Show the "seed the database" hint when the clinic has no cases at all. */
  emptyAll?: boolean;
}) {
  const visible = filter
    ? cases.filter((c) =>
        filter === "high" || filter === "medium" || filter === "low"
          ? c.priority === filter
          : stageFor(c.status)?.key === filter,
      )
    : cases;

  return (
    <Panel
      eyebrow={eyebrow}
      title={filter ? `${visible.length} of ${cases.length} — ${title}` : title}
      bodyClassName=""
      actions={
        <div className="flex items-center gap-1">
          {/* Written out rather than interpolated — Tailwind only emits
              classes it can see as literal strings. */}
          {(
            [
              ["high", "border-high/60 bg-high/12 text-high"],
              ["medium", "border-med/60 bg-med/12 text-med"],
              ["low", "border-low/60 bg-low/12 text-low"],
            ] as const
          ).map(([level, activeClass]) => (
            <button
              key={level}
              onClick={() => onFilter(filter === level ? null : level)}
              className={`rounded border px-2 py-0.5 text-[11px] uppercase tracking-wide transition-colors ${
                filter === level ? activeClass : "border-line text-faint hover:text-dim"
              }`}
            >
              {level}
            </button>
          ))}
          {filter && (
            <button
              onClick={() => onFilter(null)}
              className="ml-1 text-[11px] text-faint underline underline-offset-2 hover:text-dim"
            >
              clear
            </button>
          )}
        </div>
      }
    >
      {visible.length === 0 ? (
        <div className="p-5">
          <Empty>
            {cases.length === 0 && emptyAll ? (
              <>
                No cases yet. Run{" "}
                <code className="rounded bg-raised px-1 font-mono">
                  python scripts/seed.py --reset
                </code>{" "}
                or start an intake in the patient portal.
              </>
            ) : cases.length === 0 ? (
              (empty ?? "Nothing here.")
            ) : (
              "No cases match this filter."
            )}
          </Empty>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[64rem] text-sm">
            <thead>
              <tr className="border-b border-line-soft text-left">
                {[
                  "Case",
                  "Patient",
                  "Reason for visit",
                  "Priority",
                  "Department",
                  "Doctor",
                  "Stage",
                  "Waiting",
                  "Updated",
                  "",
                ].map((heading) => (
                  <th key={heading} className="eyebrow px-4 py-2.5 font-semibold">
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => {
                const stage = stageFor(item.status);
                const patient = patientLabel(item);
                return (
                  <tr
                    key={item.case_id}
                    className="group border-b border-line-soft/60 last:border-0 transition-colors hover:bg-raised/50"
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/cases/${item.case_id}`}
                        className="font-mono text-xs font-medium text-accent"
                      >
                        {caseRef(item.case_id)}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <p className="flex items-center gap-1.5 font-mono text-xs text-text">
                        {patient.name}
                        {patient.simulated && <Tag tone="info">sim</Tag>}
                      </p>
                      <p className="text-[11px] text-faint">{patient.descriptor}</p>
                    </td>
                    <td className="max-w-[18rem] truncate px-4 py-3 text-dim">
                      {item.chief_complaint ?? (
                        <span className="text-faint">Not recorded</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <PriorityTag priority={item.priority} />
                    </td>
                    <td className="px-4 py-3 text-dim">
                      {item.department ?? <span className="text-faint">—</span>}
                    </td>
                    <td className="px-4 py-3 text-dim">
                      {item.doctor_name ?? <span className="text-faint">Unassigned</span>}
                    </td>
                    <td className="px-4 py-3">
                      {stage ? (
                        <Tag tone={stage.tone}>
                          <Dot tone={stage.tone} live={stage.key === "prescreen"} />
                          {stage.label}
                        </Tag>
                      ) : (
                        <Tag tone="high">{item.status}</Tag>
                      )}
                    </td>
                    <td className="nums px-4 py-3 text-dim" suppressHydrationWarning>
                      {since(item.created_at, now)}
                    </td>
                    <td className="nums px-4 py-3 text-faint" suppressHydrationWarning>
                      {item.updated_at ? `${since(item.updated_at, now)} ago` : "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        href={`/cases/${item.case_id}`}
                        className="inline-flex items-center gap-1 text-xs text-faint transition-colors group-hover:text-accent"
                      >
                        Open
                        <icons.chevron className="text-[14px]" />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
