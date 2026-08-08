"use client";

import { useState } from "react";
import type { AgentRun, RunStatus } from "@/lib/agents";
import { Dot, Panel, Tag, duration, humanTime, icons, type Tone } from "@/lib/ui";

const STATUS_TONE: Record<RunStatus, Tone> = {
  completed: "low",
  running: "info",
  waiting: "med",
  failed: "high",
  idle: "neutral",
};

const ENGINE_LABEL: Record<AgentRun["engine"], string> = {
  llm: "language model",
  rules: "rule engine",
  deterministic: "deterministic",
  human: "human",
};

/** Renders one structured artefact. Values only — never model reasoning. */
export function KeyValues({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(
    ([, value]) => value !== null && value !== undefined && value !== "",
  );
  if (entries.length === 0)
    return <p className="text-xs text-faint">No output recorded.</p>;

  return (
    <dl className="space-y-1.5">
      {entries.map(([key, value]) => (
        <div key={key} className="grid grid-cols-[8.5rem_minmax(0,1fr)] gap-2">
          <dt className="font-mono text-[11px] text-faint">{key}</dt>
          <dd className="text-xs text-dim">
            {Array.isArray(value) ? (
              value.length === 0 ? (
                <span className="text-faint">none</span>
              ) : (
                <span className="flex flex-wrap gap-1">
                  {value.map((entry, index) => (
                    <Tag key={index}>{String(entry)}</Tag>
                  ))}
                </span>
              )
            ) : typeof value === "object" ? (
              <code className="break-all font-mono text-[11px]">
                {JSON.stringify(value)}
              </code>
            ) : (
              String(value)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * The per-case agent trace. Click a step to see what it received, what it
 * produced and which evidence it cited.
 */
export default function AgentRail({ runs }: { runs: AgentRun[] }) {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <Panel
      eyebrow="Execution"
      title="Agent activity"
      bodyClassName="p-2"
      actions={
        <span className="text-[11px] text-faint">
          {runs.filter((r) => r.status === "completed").length}/{runs.length} done
        </span>
      }
    >
      <ol>
        {runs.map((run, index) => {
          const expanded = open === run.key;
          const tone = STATUS_TONE[run.status];
          return (
            <li key={run.key} className="relative">
              {index < runs.length - 1 && (
                <span
                  className={`absolute left-[1.16rem] top-8 h-[calc(100%-1.4rem)] w-px ${
                    run.status === "completed" ? "bg-accent/30" : "bg-line"
                  }`}
                />
              )}
              <button
                onClick={() => setOpen(expanded ? null : run.key)}
                className={`relative flex w-full items-center gap-3 rounded px-2.5 py-2 text-left transition-colors hover:bg-raised ${
                  expanded ? "bg-raised" : ""
                }`}
              >
                <span
                  className={`z-10 grid size-[1.15rem] shrink-0 place-items-center rounded-full border bg-surface text-[10px] ${
                    run.status === "completed"
                      ? "border-low/50 text-low"
                      : run.status === "running"
                        ? "border-info text-info"
                        : run.status === "waiting"
                          ? "border-med text-med"
                          : run.status === "failed"
                            ? "border-high text-high"
                            : "border-line text-faint"
                  }`}
                >
                  {run.status === "completed" ? (
                    <icons.check className="text-[11px]" />
                  ) : (
                    <Dot tone={tone} live={run.status === "running"} />
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-text">
                    {run.name}
                  </span>
                  <span className="block text-[11px] text-faint">
                    {run.status === "idle" ? "not run" : run.status}
                    {run.at ? ` · ${humanTime(run.at)}` : ""}
                  </span>
                </span>
                <span className="nums shrink-0 font-mono text-[11px] text-dim">
                  {run.status === "waiting"
                    ? "waiting"
                    : run.elapsedMs !== null
                      ? duration(run.elapsedMs)
                      : "—"}
                </span>
              </button>

              {expanded && (
                <div className="ml-[1.7rem] mr-2 mb-2 space-y-3 rounded border border-line bg-ink/60 p-3">
                  <p className="text-xs leading-5 text-dim">{run.role}</p>

                  <div className="flex flex-wrap gap-1.5">
                    <Tag tone={run.engine === "rules" ? "accent" : "neutral"}>
                      {ENGINE_LABEL[run.engine]}
                    </Tag>
                    <Tag tone={tone}>{run.status}</Tag>
                    {run.at && <Tag>{humanTime(run.at)}</Tag>}
                    <Tag>elapsed {duration(run.elapsedMs)}</Tag>
                  </div>

                  <div>
                    <p className="eyebrow mb-1">Input artefacts</p>
                    {run.inputs.length ? (
                      <ul className="space-y-0.5">
                        {run.inputs.map((input) => (
                          <li key={input} className="font-mono text-[11px] text-dim">
                            {input}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs text-faint">None recorded.</p>
                    )}
                  </div>

                  <div>
                    <p className="eyebrow mb-1">Structured output</p>
                    {run.output ? (
                      <KeyValues data={run.output} />
                    ) : (
                      <p className="text-xs text-faint">Not produced yet.</p>
                    )}
                  </div>

                  {run.evidence.length > 0 && (
                    <div>
                      <p className="eyebrow mb-1">Evidence</p>
                      <div className="flex flex-wrap gap-1">
                        {run.evidence.map((item, index) => (
                          <Tag key={index} tone="accent">
                            {item}
                          </Tag>
                        ))}
                      </div>
                    </div>
                  )}

                  {run.note && (
                    <p className="flex gap-1.5 border-t border-line-soft pt-2 text-[11px] leading-4 text-faint">
                      <icons.alert className="mt-px shrink-0 text-[13px]" />
                      {run.note}
                    </p>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}
