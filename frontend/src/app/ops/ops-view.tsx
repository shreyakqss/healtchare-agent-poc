"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import {
  PIPELINE,
  aggregate,
  currentStep,
  mean,
  type AgentRun,
  type RunStatus,
  type StreamMetrics,
  type TimelineEntry,
  type VoiceMetrics,
} from "@/lib/agents";
import type { CaseListItem } from "@/lib/api";
import {
  Banner,
  Button,
  Dot,
  Empty,
  Metric,
  PageHeader,
  Panel,
  PriorityTag,
  Spark,
  Tag,
  caseRef,
  duration,
  humanTime,
  icons,
} from "@/lib/ui";
import WorkflowGraph, { type GraphNode } from "./workflow-graph";

/**
 * The voice channel, reported separately from the agent pipeline on purpose.
 *
 * Voice is an interface to intake, not a step in it: speech becomes a
 * transcript, the transcript goes through the ordinary intake turn, and the
 * reply is read back. Showing the three stages side by side is what makes it
 * visible that the middle one — the healthcare workflow — is unchanged and
 * timed independently of the voice layer around it.
 */
function VoicePanel({ voice }: { voice: VoiceMetrics }) {
  const stt = mean(voice.sttMs);
  const agent = mean(voice.agentMs);
  const tts = mean(voice.ttsMs);
  const round = [stt, agent, tts].filter((v): v is number => v !== null);
  const total = round.length === 3 ? round.reduce((a, b) => a + b, 0) : null;
  const widest = Math.max(1, stt ?? 0, agent ?? 0, tts ?? 0);

  const STAGES = [
    { label: "Speech-to-text", detail: "moonshine · local", ms: stt, tone: "info" as const },
    {
      label: "Healthcare workflow",
      detail: "extractor + question planner",
      ms: agent,
      tone: "accent" as const,
    },
    {
      label: "Text-to-speech",
      detail: "kokoro · local · per phrase",
      ms: tts,
      tone: "info" as const,
    },
  ];

  return (
    <Panel
      className="mt-5"
      eyebrow="Input channel"
      title="Voice"
      actions={
        <span className="flex items-center gap-2 text-[11px] text-faint">
          <icons.mic className="text-[13px]" />
          {voice.interactions} spoken {voice.interactions === 1 ? "turn" : "turns"}
        </span>
      }
    >
      {voice.interactions === 0 ? (
        <Empty>
          No voice turns yet. Switch the patient portal to Voice mode to record one.
        </Empty>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
          <div>
            <p className="eyebrow mb-3">Round trip</p>
            <ol className="space-y-2.5">
              {STAGES.map((stage, index) => (
                <li key={stage.label}>
                  <div className="flex items-center gap-3">
                    <Dot tone={stage.tone} />
                    <span className="w-44 shrink-0 text-sm text-dim">
                      {stage.label}
                      <span className="block text-[10px] text-faint">{stage.detail}</span>
                    </span>
                    <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-line-soft">
                      <span
                        className="block h-full rounded-full"
                        style={{
                          width: `${((stage.ms ?? 0) / widest) * 100}%`,
                          background: `var(--color-${stage.tone})`,
                        }}
                      />
                    </span>
                    <span className="nums w-16 shrink-0 text-right font-mono text-xs text-dim">
                      {duration(stage.ms)}
                    </span>
                  </div>
                  {index < STAGES.length - 1 && (
                    <span className="ml-[0.18rem] block h-2 w-px bg-line" />
                  )}
                </li>
              ))}
            </ol>
            <p className="mt-3 border-t border-line-soft pt-2.5 text-[11px] leading-4 text-faint">
              Averages of real per-stage timings from the audit trail. The middle
              stage is the same workflow a typed turn runs; the voice layer adds
              only the two ends and makes no clinical decision.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Metric
              label="Voice turns"
              value={voice.interactions}
              hint="reached the agents"
              tone="accent"
            />
            <Metric
              label="Round trip"
              value={duration(total)}
              hint="the three stage means, added"
            />
            <Metric
              label="STT failures"
              value={voice.sttFailures}
              hint="unusable or silent audio"
              tone={voice.sttFailures ? "high" : "neutral"}
            />
            <Metric
              label="TTS failures"
              value={voice.ttsFailures}
              hint="reply still shown as text"
              tone={voice.ttsFailures ? "high" : "neutral"}
            />
            <Metric
              label="Discarded captures"
              value={voice.discardedCaptures}
              hint="recorded, never transcribed"
              tone={voice.discardedCaptures ? "med" : "neutral"}
            />
            <div className="rounded-md border border-dashed border-line px-4 py-3 text-[11px] leading-4 text-faint">
              Playback interruptions are handled in the browser and are not
              recorded server-side, so they are not counted here.
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}

/**
 * What streaming made visible.
 *
 * The reply used to be one opaque wait; now the wait is split into the part
 * before the patient sees anything and the part they spend reading it arrive.
 * Both are measured, per reply, from the audit trail — and the speech numbers
 * beside them are the same generation being heard rather than a second one.
 */
function StreamPanel({ stream }: { stream: StreamMetrics }) {
  const ttft = mean(stream.ttftMs);
  const generation = mean(stream.generationMs);
  const chunks = mean(stream.chunks);
  const characters = mean(stream.characters);
  const firstAudio = mean(stream.firstAudioMs);
  const spoken = stream.speechSegments.reduce((a, b) => a + b, 0);

  return (
    <Panel
      className="mt-5"
      eyebrow="Response generation"
      title="Streaming"
      actions={
        <span className="flex items-center gap-2 text-[11px] text-faint">
          <icons.pulse className="text-[13px]" />
          {stream.responses} {stream.responses === 1 ? "reply" : "replies"}
        </span>
      }
    >
      {stream.responses === 0 ? (
        <Empty>
          No replies generated yet. Answer a question in the patient portal to
          record one.
        </Empty>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
          <div>
            <p className="eyebrow mb-3">One reply, in order</p>
            <ol className="space-y-2.5">
              {[
                {
                  label: "Turn accepted → first chunk",
                  detail: "extraction, then the model starts writing",
                  ms: ttft,
                  tone: "med" as const,
                },
                {
                  label: "First chunk → last chunk",
                  detail: "the patient is reading while this runs",
                  ms: generation,
                  tone: "accent" as const,
                },
                {
                  label: "First phrase spoken",
                  detail: "synthesis of segment 0, voice turns only",
                  ms: firstAudio,
                  tone: "info" as const,
                },
              ].map((stage) => (
                <li key={stage.label} className="flex items-center gap-3">
                  <Dot tone={stage.tone} />
                  <span className="w-56 shrink-0 text-sm text-dim">
                    {stage.label}
                    <span className="block text-[10px] text-faint">{stage.detail}</span>
                  </span>
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-line-soft">
                    <span
                      className="block h-full rounded-full"
                      style={{
                        width: `${((stage.ms ?? 0) / Math.max(1, ttft ?? 0, generation ?? 0, firstAudio ?? 0)) * 100}%`,
                        background: `var(--color-${stage.tone})`,
                      }}
                    />
                  </span>
                  <span className="nums w-16 shrink-0 text-right font-mono text-xs text-dim">
                    {duration(stage.ms)}
                  </span>
                </li>
              ))}
            </ol>
            <p className="mt-3 border-t border-line-soft pt-2.5 text-[11px] leading-4 text-faint">
              Means of real per-reply timings. The second bar is time the
              patient no longer waits through: before streaming, nothing was
              shown until it had finished.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Metric
              label="First chunk"
              value={duration(ttft)}
              hint="until text appears"
              tone="accent"
            />
            <Metric
              label="Generating"
              value={duration(generation)}
              hint="visible while it runs"
            />
            <Metric
              label="Chunks"
              value={chunks === null ? "—" : Math.round(chunks)}
              hint="per reply, mean"
            />
            <Metric
              label="Reply length"
              value={characters === null ? "—" : `${Math.round(characters)} ch`}
              hint="one stored message each"
            />
            <Metric
              label="Spoken phrases"
              value={spoken}
              hint="sentence-level, not per token"
            />
            <Metric
              label="Synthesis time"
              value={duration(stream.ttsTotalMs || null)}
              hint={`${stream.ttsSegments} calls, overlapping playback`}
            />
          </div>
        </div>
      )}
    </Panel>
  );
}

/** Everything the operations centre knows about one case. Derived server-side. */
export type OpsCase = {
  item: CaseListItem;
  runs: AgentRun[];
  trace: TimelineEntry[];
};

const REPLAY_INTERVAL_MS = 850;

const STEP_TONE: Record<RunStatus, "info" | "low" | "med" | "high" | "neutral"> = {
  running: "info",
  completed: "low",
  waiting: "med",
  failed: "high",
  idle: "neutral",
};

export default function OpsView({
  cases,
  voice,
  stream,
  error,
}: {
  cases: OpsCase[];
  voice: VoiceMetrics;
  stream: StreamMetrics;
  error: string | null;
}) {
  const router = useRouter();
  const [selectedId, setSelectedId] = useState(cases[0]?.item.case_id ?? null);
  const [replayIndex, setReplayIndex] = useState<number | null>(null);
  const [live, setLive] = useState(false);
  // Intervals are started from click handlers, never from an effect.
  const replayTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const liveTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const selected = cases.find((c) => c.item.case_id === selectedId) ?? cases[0] ?? null;

  /* --- replay ----------------------------------------------------------- */

  function stopReplay() {
    if (replayTimer.current) clearInterval(replayTimer.current);
    replayTimer.current = null;
    setReplayIndex(null);
  }

  function startReplay() {
    if (!selected || selected.trace.length === 0) return;
    stopReplay();
    setReplayIndex(0);
    replayTimer.current = setInterval(() => {
      setReplayIndex((index) => {
        if (index === null) return null;
        if (index >= selected.trace.length - 1) {
          if (replayTimer.current) clearInterval(replayTimer.current);
          replayTimer.current = null;
          return index;
        }
        return index + 1;
      });
    }, REPLAY_INTERVAL_MS);
  }

  function toggleLive() {
    if (liveTimer.current) {
      clearInterval(liveTimer.current);
      liveTimer.current = null;
      setLive(false);
      return;
    }
    setLive(true);
    liveTimer.current = setInterval(() => router.refresh(), 4000);
  }

  const replaying = replayIndex !== null;

  /* --- graph state ------------------------------------------------------ */

  const stats = aggregate(cases.map((c) => c.runs));

  /** Replay drives the graph when active; otherwise it aggregates all cases. */
  const nodes: GraphNode[] = PIPELINE.map((meta, index) => {
    const stat = stats[index];
    const perCase = cases.map((c) => c.runs.find((r) => r.key === meta.key)!);

    let status: RunStatus;
    if (replaying && selected) {
      const seen = selected.trace.slice(0, replayIndex! + 1);
      const currentEvent = seen[seen.length - 1];
      const touched = new Set(seen.map((entry) => entry.step).filter(Boolean));
      status =
        currentEvent?.step === meta.key
          ? "running"
          : touched.has(meta.key)
            ? "completed"
            : "idle";
    } else {
      status = perCase.some((r) => r.status === "running")
        ? "running"
        : perCase.some((r) => r.status === "waiting")
          ? "waiting"
          : perCase.some((r) => r.status === "failed")
            ? "failed"
            : perCase.some((r) => r.status === "completed")
              ? "completed"
              : "idle";
    }

    const latest = perCase
      .map((r) => r.elapsedMs)
      .filter((ms): ms is number => ms !== null);

    return {
      key: meta.key,
      name: meta.name,
      engine: meta.engine,
      status,
      executions: stat.runs,
      latestMs: latest.length ? latest[latest.length - 1] : null,
    };
  });

  /* --- global metrics --------------------------------------------------- */

  const activeCases = cases.filter(
    (c) => !["COMPLETED", "REJECTED"].includes(c.item.status),
  ).length;
  const completed = cases.filter((c) => c.item.status === "COMPLETED").length;
  const running = cases.filter((c) => c.item.status === "ANALYZING").length;
  const reviewQueue = cases.filter((c) => c.item.status === "NEEDS_REVIEW").length;
  const failed = cases.filter((c) =>
    ["FAILED", "REJECTED"].includes(c.item.status),
  ).length;
  const allSamples = stats.flatMap((s) => s.samples);
  const avgLatency = allSamples.length
    ? allSamples.reduce((a, b) => a + b, 0) / allSamples.length
    : null;
  const maxAvg = Math.max(1, ...stats.map((s) => s.avgMs ?? 0));

  return (
    <>
      <PageHeader
        eyebrow="Multi-agent runtime"
        title="AI Operations Center"
        subtitle="Every agent in the patient-care pipeline, what it produced, and how long it took. Timings are real elapsed times read back from the audit trail."
        actions={
          <>
            <Button onClick={toggleLive} variant={live ? "primary" : "ghost"}>
              {live ? <icons.stop className="text-[13px]" /> : <icons.play className="text-[13px]" />}
              {live ? "Live" : "Go live"}
            </Button>
            <Button onClick={() => router.refresh()}>
              <icons.refresh className="text-[15px]" />
              Refresh
            </Button>
          </>
        }
      />

      {error && (
        <div className="mb-5">
          <Banner tone="error">{error}</Banner>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Metric label="Active cases" value={activeCases} hint="in the pipeline" tone="accent" icon={<icons.users />} />
        <Metric label="Completed" value={completed} hint="summary released" tone="low" icon={<icons.check />} />
        <Metric
          label="Agents running"
          value={running}
          hint="graphs executing now"
          tone={running ? "info" : "neutral"}
          icon={<icons.pulse />}
        />
        <Metric
          label="Avg step latency"
          value={duration(avgLatency)}
          hint={`${allSamples.length} timed steps`}
          icon={<icons.clock />}
        />
        <Metric label="Failed runs" value={failed} hint="rejected or failed" tone={failed ? "high" : "neutral"} icon={<icons.alert />} />
        <Metric label="Review queue" value={reviewQueue} hint="waiting on a human" tone="med" icon={<icons.stethoscope />} />
      </div>

      {/* --- live workflow ------------------------------------------------ */}
      <Panel
        className="mt-5"
        eyebrow="Pipeline"
        title="Live multi-agent workflow"
        actions={
          <div className="flex items-center gap-3">
            {replaying && selected && (
              <span className="flex items-center gap-2 text-[11px] text-info">
                <Dot tone="info" live />
                replaying {caseRef(selected.item.case_id)} · step {replayIndex! + 1}/
                {selected.trace.length}
              </span>
            )}
            <span className="hidden items-center gap-3 text-[11px] text-faint lg:flex">
              {(
                [
                  ["running", "info"],
                  ["completed", "low"],
                  ["waiting", "med"],
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
        {cases.length === 0 ? (
          <Empty>No cases to trace yet.</Empty>
        ) : (
          <WorkflowGraph nodes={nodes} />
        )}
      </Panel>

      <div className="mt-5 grid items-start gap-5 xl:grid-cols-[minmax(0,23rem)_minmax(0,1fr)_minmax(0,25rem)]">
        {/* --- concurrent cases ------------------------------------------ */}
        <Panel
          eyebrow="Concurrency"
          title="Active cases"
          bodyClassName="p-2"
          actions={<span className="text-[11px] text-faint">{cases.length}</span>}
        >
          {cases.length === 0 ? (
            <div className="p-3">
              <Empty>Nothing running.</Empty>
            </div>
          ) : (
            <ul className="max-h-[26rem] space-y-1 overflow-y-auto">
              {cases.map(({ item, runs }) => {
                const step = currentStep(runs);
                const isSelected = item.case_id === selected?.item.case_id;
                return (
                  <li key={item.case_id}>
                    <button
                      onClick={() => {
                        stopReplay();
                        setSelectedId(item.case_id);
                      }}
                      className={`flex w-full items-center gap-3 rounded border px-3 py-2.5 text-left transition-colors ${
                        isSelected
                          ? "border-accent/40 bg-accent/6"
                          : "border-transparent hover:bg-raised"
                      }`}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span className="font-mono text-xs text-accent">
                            {caseRef(item.case_id)}
                          </span>
                          <PriorityTag priority={item.priority} />
                        </span>
                        <span className="mt-1 block truncate text-[11px] text-faint">
                          {item.chief_complaint ?? "No reason recorded"}
                        </span>
                      </span>
                      <span className="shrink-0 text-right">
                        <span className="block text-[11px] text-dim">
                          {step?.name ?? "—"}
                        </span>
                        <span className="mt-0.5 flex items-center justify-end gap-1.5 text-[10px] text-faint">
                          <Dot
                            tone={STEP_TONE[step?.status ?? "idle"]}
                            live={step?.status === "running"}
                          />
                          {step?.status ?? "idle"}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>

        {/* --- agent performance ----------------------------------------- */}
        <Panel
          eyebrow="Telemetry"
          title="Agent performance"
          bodyClassName=""
          actions={
            <span className="text-[11px] text-faint">across {cases.length} cases</span>
          }
        >
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line-soft text-left">
                {["Agent", "Engine", "Runs", "Avg latency", "", "Errors"].map((heading) => (
                  <th key={heading} className="eyebrow px-4 py-2 font-semibold">
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stats.map((stat) => (
                <tr
                  key={stat.key}
                  className="border-b border-line-soft/60 last:border-0 hover:bg-raised/40"
                >
                  <td className="px-4 py-2.5 text-[13px] text-text">{stat.name}</td>
                  <td className="px-4 py-2.5">
                    <Tag tone={stat.engine === "rules" ? "accent" : "neutral"}>
                      {stat.engine}
                    </Tag>
                  </td>
                  <td className="nums px-4 py-2.5 text-dim">{stat.runs}</td>
                  <td className="nums px-4 py-2.5 font-mono text-xs text-dim">
                    {stat.avgMs === null ? (
                      <span className="text-faint">not recorded</span>
                    ) : (
                      duration(stat.avgMs)
                    )}
                  </td>
                  <td className="w-32 px-4 py-2.5">
                    {stat.avgMs === null ? (
                      <span className="text-faint">—</span>
                    ) : (
                      <span className="block h-1.5 overflow-hidden rounded-full bg-line-soft">
                        <span
                          className="block h-full rounded-full bg-info"
                          style={{ width: `${(stat.avgMs / maxAvg) * 100}%` }}
                        />
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={stat.failures ? "text-high" : "text-faint"}>
                      {stat.failures}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-line-soft px-4 py-2.5 text-[11px] leading-4 text-faint">
            Latency is the elapsed time between consecutive audit events. The two
            intake agents write no audit row, so their duration is reported as not
            recorded rather than estimated.
          </p>
        </Panel>

        {/* --- trace ------------------------------------------------------ */}
        <Panel
          eyebrow="Distributed trace"
          title={selected ? `Case ${caseRef(selected.item.case_id)}` : "Execution timeline"}
          bodyClassName="p-4"
          actions={
            selected && (
              <div className="flex items-center gap-2">
                <Button
                  onClick={replaying ? stopReplay : startReplay}
                  variant={replaying ? "ghost" : "primary"}
                  disabled={selected.trace.length === 0}
                  className="px-2.5 py-1 text-xs"
                >
                  {replaying ? (
                    <icons.stop className="text-[12px]" />
                  ) : (
                    <icons.play className="text-[12px]" />
                  )}
                  {replaying ? "Stop" : "Replay case"}
                </Button>
                <Link
                  href={`/cases/${selected.item.case_id}`}
                  className="text-[11px] text-faint hover:text-accent"
                >
                  open
                </Link>
              </div>
            )
          }
        >
          {!selected || selected.trace.length === 0 ? (
            <Empty>Select a case to trace its execution.</Empty>
          ) : (
            <ol className="max-h-[26rem] space-y-0 overflow-y-auto pr-1">
              {selected.trace.map((entry, index) => {
                const reached = !replaying || index <= replayIndex!;
                const isCurrent = replaying && index === replayIndex;
                return (
                  <li
                    key={entry.id}
                    className={`relative flex gap-3 rounded px-1.5 py-1.5 transition-colors ${
                      isCurrent ? "bg-info/10" : ""
                    } ${reached ? "" : "opacity-30"}`}
                  >
                    {index < selected.trace.length - 1 && (
                      <span className="absolute left-[4.2rem] top-6 h-full w-px bg-line" />
                    )}
                    <span
                      className="nums w-14 shrink-0 pt-px font-mono text-[10px] text-faint"
                      suppressHydrationWarning
                    >
                      {humanTime(entry.at)}
                    </span>
                    <span
                      className={`z-10 mt-1.5 size-1.5 shrink-0 rounded-full ring-4 ring-surface ${
                        isCurrent ? "bg-info running-dot" : "bg-accent/60"
                      }`}
                    />
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
                );
              })}
            </ol>
          )}
        </Panel>
      </div>

      {/* --- response generation ------------------------------------------ */}
      <StreamPanel stream={stream} />

      {/* --- voice channel ------------------------------------------------ */}
      <VoicePanel voice={voice} />

      {/* --- throughput per agent ---------------------------------------- */}
      <Panel className="mt-5" eyebrow="Distribution" title="Executions per agent">
        <div className="grid gap-4 sm:grid-cols-3 xl:grid-cols-5">
          {stats
            .filter((stat) => stat.runs > 0)
            .map((stat) => (
              <div key={stat.key} className="rounded border border-line bg-raised/30 px-3 py-2.5">
                <p className="truncate text-[11px] text-dim">{stat.name}</p>
                <div className="mt-1 flex items-end justify-between gap-2">
                  <span className="nums text-xl font-semibold">{stat.runs}</span>
                  <Spark values={stat.samples} width={64} height={22} />
                </div>
              </div>
            ))}
        </div>
      </Panel>
    </>
  );
}
