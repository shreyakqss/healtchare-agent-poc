"use client";

import Link from "next/link";
import type { PatientProfile } from "@/lib/api";
import {
  PHASE_LABEL,
  elapsed,
  laneRuns,
  type SimPhase,
  type SimRun,
} from "@/lib/simulation";
import {
  Button,
  Dot,
  PriorityTag,
  Tag,
  caseRef,
  icons,
  titleCase,
  type Tone,
} from "@/lib/ui";
import WorkflowGraph, { type GraphNode } from "../ops/workflow-graph";

export const PHASE_TONE: Record<SimPhase, Tone> = {
  queued: "neutral",
  intake: "info",
  prescreen: "info",
  review: "med",
  consultation: "accent",
  final: "info",
  done: "low",
  stopped: "neutral",
  failed: "high",
};

const initials = (name: string) =>
  name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

/** Small round avatar. Colour is keyed to the lane so patients stay apart. */
export function Avatar({ name, tone = "accent" }: { name: string; tone?: Tone }) {
  const fill = {
    neutral: "bg-raised text-dim",
    accent: "bg-accent/12 text-accent ring-accent/30",
    info: "bg-info/12 text-info ring-info/30",
    high: "bg-high/12 text-high ring-high/30",
    med: "bg-med/12 text-med ring-med/30",
    low: "bg-low/12 text-low ring-low/30",
  }[tone];
  return (
    <span
      className={`grid size-8 shrink-0 place-items-center rounded-full text-[11px] font-semibold ring-1 ${fill}`}
    >
      {initials(name)}
    </span>
  );
}

/* --- the picker ----------------------------------------------------------- */

/** One selectable Synthea record. The chips are the record, not a summary. */
export function PatientCard({
  profile,
  selected,
  disabled,
  onToggle,
}: {
  profile: PatientProfile;
  selected: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      disabled={disabled}
      aria-pressed={selected}
      className={`flex h-full w-full flex-col rounded-md border px-3.5 py-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
        selected
          ? "border-accent/45 bg-accent/6"
          : "border-line bg-surface/60 hover:border-faint"
      }`}
    >
      <span className="flex items-center gap-2.5">
        <Avatar name={profile.name} tone={selected ? "accent" : "neutral"} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium text-text">
            {profile.name}
          </span>
          <span className="block text-[11px] text-faint">
            {profile.age} · {profile.gender === "F" ? "female" : "male"}
          </span>
        </span>
        <span
          className={`grid size-4 shrink-0 place-items-center rounded border text-[10px] ${
            selected ? "border-accent bg-accent text-on-accent" : "border-line text-transparent"
          }`}
        >
          <icons.check className="text-[10px]" />
        </span>
      </span>

      <span className="mt-2.5 block text-xs leading-4 text-dim">{profile.headline}</span>

      <span className="mt-2.5 flex flex-wrap gap-1">
        {profile.conditions.map((entry) => (
          <Tag key={entry.code} tone="info">
            {entry.description}
          </Tag>
        ))}
        {profile.medications.map((entry) => (
          <Tag key={entry.code}>
            <icons.pill className="text-[11px]" />
            {entry.description.split(" ")[0]}
          </Tag>
        ))}
        {profile.allergies.map((entry) => (
          <Tag key={entry.code} tone="high">
            <icons.alert className="text-[11px]" />
            {entry.description}
          </Tag>
        ))}
      </span>

      {profile.expectation && (
        <span className="mt-auto block pt-2.5 text-[10px] uppercase tracking-wide text-faint">
          {profile.expectation}
        </span>
      )}
    </button>
  );
}

/* --- one running patient -------------------------------------------------- */

/**
 * One patient's lane: who they are, where they are, and the whole agent
 * pipeline drawn for their case alone. Three of these side by side is the
 * point of the page — the same nine agents, running independently per case.
 */
export function PatientLane({
  run,
  now,
  focused,
  onFocus,
  onApprove,
}: {
  run: SimRun;
  now: number;
  focused: boolean;
  onFocus: () => void;
  onApprove: () => void;
}) {
  const nodes: GraphNode[] = laneRuns(run).map((agent) => ({
    key: agent.key,
    name: agent.name,
    engine: agent.engine,
    status: agent.status,
    executions:
      typeof agent.output?.runs === "number"
        ? agent.output.runs
        : agent.status === "idle"
          ? 0
          : 1,
    latestMs: agent.elapsedMs,
  }));

  const tone = PHASE_TONE[run.phase];
  const ms = elapsed(run, now);
  const done = run.runs.filter((agent) => agent.status === "completed").length;

  return (
    <section
      className={`rounded-md border bg-surface/80 transition-colors ${
        focused ? "border-accent/45" : "border-line"
      }`}
    >
      <header className="flex flex-wrap items-center gap-3 border-b border-line-soft px-4 py-2.5">
        <Avatar name={run.profile.name} tone={tone} />
        <button onClick={onFocus} className="min-w-0 text-left">
          <span className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold text-text">
              {run.profile.name}
            </span>
            {run.caseId && (
              <span className="font-mono text-[11px] text-accent">
                {caseRef(run.caseId)}
              </span>
            )}
          </span>
          <span className="block truncate text-[11px] text-faint">
            {run.profile.headline}
          </span>
        </button>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          {run.detail?.triage && <PriorityTag priority={run.detail.triage.priority} />}
          {run.detail?.routing?.specialty && (
            <Tag tone="info">
              <icons.route className="text-[11px]" />
              {run.detail.routing.specialty}
              {run.detail.routing.doctor_name ? ` · ${run.detail.routing.doctor_name}` : ""}
            </Tag>
          )}
          <Tag tone={tone}>
            <Dot tone={tone} live={run.phase !== "done" && run.phase !== "queued"} />
            {PHASE_LABEL[run.phase]}
          </Tag>
          <span className="nums w-14 text-right font-mono text-[11px] text-dim">
            {ms === null ? "—" : `${(ms / 1000).toFixed(1)}s`}
          </span>
          {run.caseId && (
            <Link
              href={`/cases/${run.caseId}`}
              className="text-[11px] text-faint hover:text-accent"
            >
              open
            </Link>
          )}
        </div>
      </header>

      <div className="px-4 py-3">
        {run.runs.length > 0 ? (
          <WorkflowGraph nodes={nodes} />
        ) : (
          <p className="py-4 text-center text-xs text-faint">
            Waiting for the first agent to run…
          </p>
        )}

        <div className="mt-3 flex flex-wrap items-start gap-3 border-t border-line-soft pt-3">
          <span className="flex min-w-0 flex-1 items-start gap-2">
            <Dot tone={tone} live={run.phase !== "done"} />
            <span className="min-w-0">
              <span className="block text-xs leading-4 text-dim">{run.activity}</span>
              {run.streaming && (
                <span className="mt-1 block border-l-2 border-info/40 pl-2 text-xs italic leading-4 text-faint">
                  {run.streaming}
                  <span className="ml-0.5 inline-block h-3 w-px animate-pulse bg-info align-middle" />
                </span>
              )}
            </span>
          </span>

          <span className="flex shrink-0 items-center gap-3 text-[11px] text-faint">
            <span>{done}/9 agents</span>
            <span>{run.turns} turns</span>
            {run.replySource && (
              <Tag tone={run.replySource === "llm" ? "neutral" : "med"}>
                patient: {run.replySource === "llm" ? "model" : "record"}
              </Tag>
            )}
          </span>

          {run.awaitingReview && (
            <Button variant="primary" onClick={onApprove} className="px-2.5 py-1 text-xs">
              <icons.stethoscope className="text-[13px]" />
              Approve as clinician
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}

/* --- record vs. recovered ------------------------------------------------- */

/**
 * What the Synthea record says, beside what the agents pulled out of the
 * conversation.
 *
 * This is the check the demo is really making: the record never reaches the
 * workflow, only the patient's sentences do, so every row on the right had to
 * be recovered from language by the extractor. A blank right-hand cell is a
 * real gap, not a rendering placeholder.
 */
export function RecordComparison({ run }: { run: SimRun }) {
  const detail = run.detail;

  const recovered = (field: string): string[] => {
    if (!detail) return [];
    if (field === "allergy" || field === "medication") {
      return detail.allergies_medications
        .filter((entry) => entry.kind === field)
        .map((entry) => entry.name);
    }
    return detail.facts
      .filter((fact) => fact.kind === field || (field === "history" && fact.kind === "condition"))
      .map((fact) => fact.value);
  };

  return (
    <ul className="divide-y divide-line-soft">
      {Object.entries(run.profile.answers).map(([field, said]) => {
        const found = recovered(field);
        return (
          <li key={field} className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3 py-2.5">
            <span className="font-mono text-[11px] text-faint">{titleCase(field)}</span>
            <span className="min-w-0">
              <span className="block text-xs leading-4 text-dim">{said}</span>
              <span className="mt-1 flex flex-wrap items-center gap-1">
                {found.length ? (
                  found.map((value, index) => (
                    <Tag key={index} tone="low">
                      <icons.check className="text-[11px]" />
                      {value}
                    </Tag>
                  ))
                ) : (
                  <span className="text-[11px] text-faint">not recovered yet</span>
                )}
              </span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
