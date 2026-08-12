"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiError, api, type CaseListItem } from "@/lib/api";
import {
  BarList,
  Banner,
  Button,
  Donut,
  Dot,
  Empty,
  Metric,
  PageHeader,
  Panel,
  PriorityTag,
  Tag,
  caseRef,
  icons,
  since,
  type Slice,
  type Tone,
} from "@/lib/ui";

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
    // Set by the simulation when it opens a case. Nothing branches on it
    // beyond this label — a simulated case is an ordinary case.
    simulated: simulated === true,
  };
}

export default function DashboardView({
  initialCases,
  initialError,
}: {
  initialCases: CaseListItem[];
  initialError: string | null;
}) {
  const [cases, setCases] = useState(initialCases);
  const [error, setError] = useState(initialError);
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
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const count = (statuses: readonly string[]) =>
    cases.filter((c) => statuses.includes(c.status)).length;

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

  const visible = filter
    ? cases.filter((c) =>
        filter === "high" || filter === "medium" || filter === "low"
          ? c.priority === filter
          : stageFor(c.status)?.key === filter,
      )
    : cases;

  return (
    <>
      <PageHeader
        eyebrow="Hospital staff"
        title="Patient queue & operations"
        subtitle="Every case currently moving through intake, AI pre-screening, clinician review and consultation."
        actions={
          <>
            <Link
              href="/simulation"
              className="inline-flex items-center gap-2 rounded border border-line px-3 py-1.5 text-sm text-dim transition-colors hover:border-faint hover:text-text"
            >
              <icons.play className="text-[13px]" />
              Fill the queue
            </Link>
            <Button onClick={() => void refresh()} disabled={busy}>
              <icons.refresh className={busy ? "animate-spin text-[15px]" : "text-[15px]"} />
              {busy ? "Refreshing" : "Refresh"}
            </Button>
          </>
        }
      />

      {error && (
        <div className="mb-5">
          <Banner tone="error">{error}</Banner>
        </div>
      )}

      {/* --- KPI strip ---------------------------------------------------- */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
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

      {/* --- analytics ---------------------------------------------------- */}
      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,20rem)_minmax(0,1fr)_minmax(0,24rem)]">
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

        <Panel eyebrow="Throughput" title="Case flow">
          <ol className="space-y-1">
            {STAGES.map((stage, index) => {
              const value = count(stage.statuses);
              const width = cases.length ? (value / cases.length) * 100 : 0;
              return (
                <li key={stage.key}>
                  <button
                    onClick={() => setFilter(filter === stage.key ? null : stage.key)}
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
      </div>

      {/* --- queue -------------------------------------------------------- */}
      <Panel
        className="mt-5"
        eyebrow="Live queue"
        title={`${visible.length} of ${cases.length} cases`}
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
                onClick={() => setFilter(filter === level ? null : level)}
                className={`rounded border px-2 py-0.5 text-[11px] uppercase tracking-wide transition-colors ${
                  filter === level ? activeClass : "border-line text-faint hover:text-dim"
                }`}
              >
                {level}
              </button>
            ))}
            {filter && (
              <button
                onClick={() => setFilter(null)}
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
              {cases.length === 0 ? (
                <>
                  No cases yet. Run{" "}
                  <code className="rounded bg-raised px-1 font-mono">
                    python scripts/seed.py --reset
                  </code>{" "}
                  or start an intake in the patient portal.
                </>
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
    </>
  );
}
