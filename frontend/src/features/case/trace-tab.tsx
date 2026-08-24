import type { AuditEvent, CaseDetail } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge, type Tone } from "@/components/ui/badge";
import { Icons } from "@/components/ui/icons";
import { cn } from "@/lib/utils";
import { deriveStages, formatLatency, type StageView } from "@/features/case/trace";

const KIND: Record<StageView["kind"], { label: string; tone: Tone; icon: keyof typeof Icons }> = {
  llm: { label: "AI model", tone: "brand", icon: "sparkles" },
  rules: { label: "Rule-based", tone: "info", icon: "shield" },
  human: { label: "Human", tone: "warning", icon: "user" },
  system: { label: "System", tone: "neutral", icon: "database" },
};

const STATUS: Record<StageView["status"], { label: string; dot: string }> = {
  done: { label: "Done", dot: "bg-success" },
  pending: { label: "Pending", dot: "bg-line-strong" },
  skipped: { label: "Skipped", dot: "bg-fg-subtle" },
  failed: { label: "Failed", dot: "bg-danger" },
};

export function TraceTab({ detail, events }: { detail: CaseDetail; events: AuditEvent[] }) {
  const stages = deriveStages(detail, events);
  const done = stages.filter((s) => s.status === "done").length;

  return (
    <Card>
      <CardHeader
        title="Agent trace"
        description="Which stage produced what, derived from the audit trail. Latency is the gap to the previous event; nothing is estimated."
        action={<Badge tone="neutral">{done}/{stages.length} stages</Badge>}
      />
      <CardBody>
        <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {stages.map((s, i) => {
            const k = KIND[s.kind];
            const Icon = Icons[k.icon];
            const st = STATUS[s.status];
            return (
              <li key={s.id} className={cn(
                "rounded-lg border p-4",
                s.status === "failed" ? "border-danger bg-danger-soft" : s.status === "done" ? "border-line bg-surface" : "border-dashed border-line bg-sunken",
              )}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="tabular text-[11px] font-semibold text-fg-subtle">{String(i + 1).padStart(2, "0")}</span>
                    <span className={cn("flex h-7 w-7 items-center justify-center rounded-md", s.status === "done" ? "bg-brand-soft text-brand" : "bg-sunken text-fg-subtle")}>
                      <Icon size={15} />
                    </span>
                    <h3 className="text-sm font-semibold">{s.name}</h3>
                  </div>
                  <span className="flex items-center gap-1.5 text-[11px] text-fg-muted">
                    <span className={cn("h-1.5 w-1.5 rounded-full", st.dot)} aria-hidden="true" /> {st.label}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <Badge tone={k.tone}>{k.label}</Badge>
                  {s.kind !== "human" ? <span className="tabular text-[11px] text-fg-subtle">{s.id === "intake" ? "avg turn " : ""}{formatLatency(s.latencyMs)}</span> : null}
                </div>
                <p className={cn("mt-2.5 text-sm leading-5", s.output ? "text-fg" : "text-fg-subtle")}>{s.output ?? "No output yet"}</p>
                {s.detail?.length ? (
                  <ul className="mt-2 space-y-0.5 text-xs text-fg-muted">{s.detail.map((d) => <li key={d}>{d}</li>)}</ul>
                ) : null}
              </li>
            );
          })}
        </ol>
        <p className="mt-4 text-xs text-fg-subtle">Priority is never set by a model: the urgency evaluator runs the clinic&rsquo;s rules only, and every output waits for the human review stage.</p>
      </CardBody>
    </Card>
  );
}