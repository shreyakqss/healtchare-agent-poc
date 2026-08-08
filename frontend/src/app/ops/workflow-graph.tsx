"use client";

import type { RunStatus } from "@/lib/agents";
import { Dot, duration, icons, type Tone } from "@/lib/ui";

export type GraphNode = {
  key: string;
  name: string;
  engine: string;
  status: RunStatus;
  executions: number;
  latestMs: number | null;
};

const NODE_STYLE: Record<RunStatus, string> = {
  running: "border-info/70 bg-info/10 shadow-[0_0_24px_-8px_var(--color-info)]",
  completed: "border-low/45 bg-low/6",
  waiting: "border-med/55 bg-med/8",
  failed: "border-high/60 bg-high/10",
  idle: "border-line bg-surface/60",
};

const STATUS_TONE: Record<RunStatus, Tone> = {
  running: "info",
  completed: "low",
  waiting: "med",
  failed: "high",
  idle: "neutral",
};

const ENGINE_GLYPH: Record<string, keyof typeof icons> = {
  llm: "pulse",
  rules: "shield",
  deterministic: "route",
  human: "stethoscope",
};

/**
 * The live pipeline. Node state is aggregated across every case in flight, or
 * driven by a replay when one is running — the same graph, two data sources.
 */
export default function WorkflowGraph({ nodes }: { nodes: GraphNode[] }) {
  return (
    <div className="flex items-stretch overflow-x-auto pb-1">
      {nodes.map((node, index) => {
        const Glyph = icons[ENGINE_GLYPH[node.engine] ?? "route"];
        const downstreamLive = nodes[index + 1]?.status === "running";
        return (
          <div key={node.key} className="flex min-w-0 flex-1 items-center">
            <div
              className={`relative min-w-[8.5rem] flex-1 rounded-md border px-3 py-2.5 transition-colors ${NODE_STYLE[node.status]}`}
            >
              <div className="flex items-center gap-1.5">
                <Glyph className="shrink-0 text-[13px] text-faint" />
                <Dot tone={STATUS_TONE[node.status]} live={node.status === "running"} />
                <span className="ml-auto shrink-0 font-mono text-[10px] uppercase tracking-wide text-faint">
                  {node.status}
                </span>
              </div>
              <p className="mt-1.5 truncate text-xs font-medium leading-4 text-text">
                {node.name}
              </p>
              <div className="mt-1.5 flex items-baseline justify-between gap-2 border-t border-line-soft pt-1.5">
                <span className="nums text-[11px] text-dim">
                  {node.executions}
                  <span className="text-faint"> runs</span>
                </span>
                <span className="nums font-mono text-[10px] text-faint">
                  {node.latestMs === null ? "—" : duration(node.latestMs)}
                </span>
              </div>
            </div>

            {index < nodes.length - 1 && (
              <svg
                width="26"
                height="12"
                viewBox="0 0 26 12"
                className="shrink-0"
                aria-hidden
              >
                <line
                  x1="1"
                  y1="6"
                  x2="21"
                  y2="6"
                  stroke={
                    downstreamLive
                      ? "var(--color-info)"
                      : node.status === "completed"
                        ? "var(--color-accent-dim)"
                        : "var(--color-line)"
                  }
                  strokeWidth="1.5"
                  className={downstreamLive ? "edge-live" : ""}
                />
                <path
                  d="M20 3l5 3-5 3z"
                  fill={
                    downstreamLive
                      ? "var(--color-info)"
                      : node.status === "completed"
                        ? "var(--color-accent-dim)"
                        : "var(--color-line)"
                  }
                />
              </svg>
            )}
          </div>
        );
      })}
    </div>
  );
}
