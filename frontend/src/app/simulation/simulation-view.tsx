"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { aggregate, timeline } from "@/lib/agents";
import type { PatientRoster } from "@/lib/api";
import {
  PHASE_LABEL,
  blankRun,
  elapsed,
  isActive,
  laneRuns,
  newControl,
  runPatient,
  type SimControl,
  type SimRun,
} from "@/lib/simulation";
import {
  Banner,
  Button,
  Dot,
  Empty,
  Metric,
  PageHeader,
  Panel,
  Tag,
  caseRef,
  duration,
  humanTime,
  icons,
} from "@/lib/ui";
import AgentRail from "../cases/[id]/agent-rail";
import { PatientCard, PatientLane, RecordComparison } from "./patient-lane";

/** Two or three at once: enough to show independence, few enough to follow. */
const MAX_PATIENTS = 3;

type Status = "idle" | "running" | "paused" | "stopped" | "done";

export default function SimulationView({
  roster,
  initialError,
}: {
  roster: PatientRoster;
  initialError: string | null;
}) {
  const [selected, setSelected] = useState<string[]>(
    roster.patients.slice(0, MAX_PATIENTS).map((patient) => patient.id),
  );
  const [runs, setRuns] = useState<Record<string, SimRun>>({});
  const [order, setOrder] = useState<string[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [hold, setHold] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const [error] = useState(initialError);
  // Read from a timer, never during render — elapsed times would otherwise be
  // a clock read in the render body, which the React Compiler rejects.
  const [now, setNow] = useState(() => Date.now());

  const control = useRef<SimControl | null>(null);
  const clock = useRef<ReturnType<typeof setInterval> | null>(null);

  const list = order.map((id) => runs[id]).filter(Boolean);
  const focused = (focus && runs[focus]) || list[0] || null;

  function stopClock() {
    if (clock.current) clearInterval(clock.current);
    clock.current = null;
    // Read inside the updater rather than the function body: the React
    // Compiler treats a bare Date.now() in a component as a render-time read.
    setNow(() => Date.now());
  }

  function toggle(id: string) {
    setSelected((current) =>
      current.includes(id)
        ? current.filter((entry) => entry !== id)
        : current.length >= MAX_PATIENTS
          ? current
          : [...current, id],
    );
  }

  /**
   * Start every selected patient at once.
   *
   * Plain concurrent promises — no queue, no scheduler. Each one drives its own
   * case through the public API, so what appears on screen is genuinely several
   * workflows in flight rather than one being animated three times.
   */
  function start() {
    const patients = roster.patients.filter((patient) => selected.includes(patient.id));
    if (patients.length === 0) return;

    const ctl = newControl(hold);
    control.current = ctl;
    setRuns(Object.fromEntries(patients.map((p) => [p.id, blankRun(p)])));
    setOrder(patients.map((p) => p.id));
    setFocus(patients[0].id);
    setStatus("running");
    setNow(() => Date.now());
    clock.current = setInterval(() => setNow(Date.now()), 500);

    void Promise.all(
      patients.map((patient) =>
        runPatient(patient, ctl, (patch) =>
          setRuns((current) => ({
            ...current,
            [patient.id]: { ...current[patient.id], ...patch },
          })),
        ),
      ),
    ).then(() => {
      stopClock();
      setStatus(ctl.stopped ? "stopped" : "done");
    });
  }

  function pause() {
    if (!control.current) return;
    control.current.paused = true;
    setStatus("paused");
  }

  function resume() {
    if (!control.current) return;
    control.current.paused = false;
    setStatus("running");
    if (!clock.current) clock.current = setInterval(() => setNow(Date.now()), 500);
  }

  function stop() {
    if (control.current) {
      control.current.stopped = true;
      control.current.paused = false;
    }
    stopClock();
    setStatus("stopped");
  }

  function reset() {
    stop();
    setRuns({});
    setOrder([]);
    setFocus(null);
    setStatus("idle");
  }

  /** Approving here is a real clinician review — it writes a ClinicalReview. */
  function approve(id: string) {
    control.current?.approved.add(id);
  }

  /* --- rollups ---------------------------------------------------------- */

  const active = list.filter(isActive).length;
  const completed = list.filter((run) => run.phase === "done").length;
  const failed = list.filter((run) => run.phase === "failed").length;
  const turns = list.reduce((total, run) => total + run.turns, 0);
  const stats = aggregate(list.map((run) => laneRuns(run)));
  const executions = stats.reduce((total, stat) => total + stat.runs, 0);
  const durations = list
    .map((run) => elapsed(run, now))
    .filter((ms): ms is number => ms !== null);
  const trace = focused ? timeline(focused.audit) : [];

  const running = status === "running";

  return (
    <>
      <PageHeader
        eyebrow="Multi-agent simulation"
        title="Patient Simulation"
        subtitle={
          <>
            Synthetic patients from{" "}
            <a
              href="https://github.com/synthetichealth/synthea"
              target="_blank"
              rel="noreferrer"
              className="text-accent hover:underline"
            >
              Synthea
            </a>{" "}
            records walk into the clinic at the same time. Each one answers the
            intake assistant from its own record, and every case is processed by
            the same nine agents, independently, from intake to visit summary.
          </>
        }
        actions={
          <>
            <label className="mr-1 flex cursor-pointer items-center gap-2 text-xs text-dim">
              <input
                type="checkbox"
                checked={hold}
                disabled={status !== "idle"}
                onChange={(event) => setHold(event.target.checked)}
                className="accent-[var(--color-accent)]"
              />
              Hold at review gate
            </label>
            {status === "idle" || status === "done" || status === "stopped" ? (
              <Button
                variant="primary"
                onClick={start}
                disabled={selected.length === 0 || roster.patients.length === 0}
              >
                <icons.play className="text-[13px]" />
                Start {selected.length} patient{selected.length === 1 ? "" : "s"}
              </Button>
            ) : (
              <Button variant="primary" onClick={running ? pause : resume}>
                {running ? (
                  <icons.stop className="text-[13px]" />
                ) : (
                  <icons.play className="text-[13px]" />
                )}
                {running ? "Pause" : "Resume"}
              </Button>
            )}
            <Button onClick={stop} disabled={status === "idle" || status === "done"}>
              <icons.stop className="text-[13px]" />
              Stop
            </Button>
            <Button onClick={reset} disabled={status === "idle"}>
              <icons.refresh className="text-[15px]" />
              Reset
            </Button>
          </>
        }
      />

      {error && (
        <div className="mb-5">
          <Banner tone="error">{error}</Banner>
        </div>
      )}

      {/* --- roster ------------------------------------------------------- */}
      <Panel
        eyebrow={roster.source === "synthea-export" ? "Synthea export" : "Synthea fixture"}
        title="Synthetic patients"
        actions={
          <span className="flex items-center gap-3 text-[11px] text-faint">
            <span>
              {selected.length}/{MAX_PATIENTS} selected
            </span>
            <Tag tone={roster.source === "synthea-export" ? "accent" : "neutral"}>
              {roster.source === "synthea-export"
                ? "generated population"
                : "bundled records"}
            </Tag>
          </span>
        }
      >
        {roster.patients.length === 0 ? (
          <Empty>
            No synthetic patients. Drop a Synthea CSV export in
            <code className="mx-1 font-mono text-[11px]">backend/data/synthea/csv</code>
            or restore <code className="font-mono text-[11px]">data/patients.yaml</code>.
          </Empty>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {roster.patients.map((patient) => (
              <PatientCard
                key={patient.id}
                profile={patient}
                selected={selected.includes(patient.id)}
                disabled={status !== "idle" && status !== "done" && status !== "stopped"}
                onToggle={() => toggle(patient.id)}
              />
            ))}
          </div>
        )}
        <p className="mt-3 border-t border-line-soft pt-2.5 text-[11px] leading-4 text-faint">
          Conditions carry SNOMED CT codes and medications RxNorm codes, as
          Synthea exports them. The record is never sent to the workflow — only
          the sentences the patient agent says are, which is what leaves the
          extractor something real to do.
        </p>
      </Panel>

      {/* --- live board --------------------------------------------------- */}
      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Metric
          label="Patients in flight"
          value={active}
          hint={`of ${list.length} started`}
          tone={active ? "info" : "neutral"}
          icon={<icons.users />}
        />
        <Metric
          label="Completed"
          value={completed}
          hint="summary released"
          tone="low"
          icon={<icons.check />}
        />
        <Metric
          label="Agent executions"
          value={executions}
          hint="across every lane"
          tone="accent"
          icon={<icons.pulse />}
        />
        <Metric
          label="Conversation turns"
          value={turns}
          hint="patient messages sent"
          icon={<icons.send />}
        />
        <Metric
          label="Longest run"
          value={durations.length ? `${(Math.max(...durations) / 1000).toFixed(1)}s` : "—"}
          hint="wall clock, end to end"
          icon={<icons.clock />}
        />
        <Metric
          label="Failed"
          value={failed}
          hint="stopped on an error"
          tone={failed ? "high" : "neutral"}
          icon={<icons.alert />}
        />
      </div>

      {/* --- lanes -------------------------------------------------------- */}
      <Panel
        className="mt-5"
        eyebrow="Concurrency"
        title="Patient journeys"
        bodyClassName="space-y-3 p-3"
        actions={
          <div className="flex items-center gap-3 text-[11px] text-faint">
            {status !== "idle" && (
              <span className="flex items-center gap-1.5">
                <Dot tone={running ? "info" : "neutral"} live={running} />
                {status}
              </span>
            )}
            <span className="hidden items-center gap-3 lg:flex">
              {(
                [
                  ["running", "info"],
                  ["completed", "low"],
                  ["waiting", "med"],
                  ["failed", "high"],
                  ["idle", "neutral"],
                ] as const
              ).map(([label, tone]) => (
                <span key={label} className="flex items-center gap-1.5">
                  <Dot tone={tone} />
                  {label}
                </span>
              ))}
            </span>
          </div>
        }
      >
        {list.length === 0 ? (
          <Empty>
            Select up to {MAX_PATIENTS} patients above and press Start. Each one
            opens its own case and runs the full pipeline.
          </Empty>
        ) : (
          list.map((run) => (
            <PatientLane
              key={run.profile.id}
              run={run}
              now={now}
              focused={focused?.profile.id === run.profile.id}
              onFocus={() => setFocus(run.profile.id)}
              onApprove={() => approve(run.profile.id)}
            />
          ))
        )}
      </Panel>

      {/* --- inspector ---------------------------------------------------- */}
      {focused && (
        <div className="mt-5 grid items-start gap-5 xl:grid-cols-[minmax(0,25rem)_minmax(0,1fr)_minmax(0,25rem)]">
          <div className="space-y-5">
            <Panel
              eyebrow="Ground truth vs. extraction"
              title={`${focused.profile.name}'s record`}
              actions={
                focused.caseId && (
                  <Link
                    href={`/cases/${focused.caseId}`}
                    className="font-mono text-[11px] text-accent hover:underline"
                  >
                    {caseRef(focused.caseId)}
                  </Link>
                )
              }
            >
              <RecordComparison run={focused} />
            </Panel>

            <Panel eyebrow="Conversation" title="Intake transcript" bodyClassName="p-3">
              {focused.transcript.length === 0 ? (
                <Empty>Nothing said yet.</Empty>
              ) : (
                <ol className="max-h-[22rem] space-y-2 overflow-y-auto pr-1">
                  {focused.transcript.map((turn, index) => (
                    <li
                      key={index}
                      className={`rounded px-2.5 py-1.5 text-xs leading-4 ${
                        turn.role === "patient"
                          ? "bg-accent/8 text-text"
                          : "bg-raised/60 text-dim"
                      }`}
                    >
                      <span className="eyebrow mb-0.5 block">
                        {turn.role === "patient" ? focused.profile.name : "Intake assistant"}
                      </span>
                      {turn.content}
                    </li>
                  ))}
                </ol>
              )}
            </Panel>
          </div>

          <AgentRail runs={laneRuns(focused)} />

          <Panel
            eyebrow="Distributed trace"
            title="Execution timeline"
            bodyClassName="p-4"
            actions={
              <span className="text-[11px] text-faint">
                {PHASE_LABEL[focused.phase]} · {trace.length} events
              </span>
            }
          >
            {trace.length === 0 ? (
              <Empty>No events recorded yet.</Empty>
            ) : (
              <ol className="max-h-[36rem] space-y-0 overflow-y-auto pr-1">
                {trace.map((entry, index) => (
                  <li key={entry.id} className="relative flex gap-3 rounded px-1.5 py-1.5">
                    {index < trace.length - 1 && (
                      <span className="absolute left-[4.2rem] top-6 h-full w-px bg-line" />
                    )}
                    <span
                      className="nums w-14 shrink-0 pt-px font-mono text-[10px] text-faint"
                      suppressHydrationWarning
                    >
                      {humanTime(entry.at)}
                    </span>
                    <span className="z-10 mt-1.5 size-1.5 shrink-0 rounded-full bg-accent/60 ring-4 ring-surface" />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline gap-2">
                        <span className="text-xs font-medium text-text">{entry.label}</span>
                        <span className="nums ml-auto shrink-0 font-mono text-[10px] text-faint">
                          +{duration(entry.offsetMs)}
                        </span>
                      </span>
                      <span className="block truncate text-[10px] text-faint">
                        {entry.actor}
                        {entry.detail && ` · ${entry.detail}`}
                      </span>
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
        </div>
      )}

      <p className="mt-5 text-center text-[11px] leading-4 text-faint">
        Simulated cases are ordinary cases. They appear in the{" "}
        <Link href="/dashboard" className="text-dim hover:text-accent">
          staff dashboard
        </Link>{" "}
        and the{" "}
        <Link href="/ops" className="text-dim hover:text-accent">
          operations centre
        </Link>{" "}
        alongside everything else, and every turn above went through the same
        endpoints the patient portal uses.
      </p>
    </>
  );
}
