import { Badge, Icons, Stat } from "@/components/ui";
import type { CaseListItem, ClinicOverview, Health, HMSStatus } from "@/lib/api/types";
import { countHighOpen, countStatus } from "@/features/clinic/derive";

export function StatsRow({ cases, overview, health, hms, hospitalId }: {
  cases: CaseListItem[]; overview: ClinicOverview | null; health: Health | null; hms: HMSStatus | null; hospitalId: string | null;
}) {
  const awaiting = overview?.awaiting_review ?? countStatus(cases, "NEEDS_REVIEW");
  const completed = overview?.completed_today ?? 0;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Awaiting review" value={awaiting} tone={awaiting ? "warning" : undefined} icon={<Icons.clock size={16} />} hint="Needs a clinician decision" />
        <Stat label="High priority, open" value={countHighOpen(cases)} tone={countHighOpen(cases) ? "danger" : undefined} icon={<Icons.flag size={16} />} hint="Rule-based, not AI" />
        <Stat label="Intake in progress" value={countStatus(cases, "INGESTING") + countStatus(cases, "CREATED")} icon={<Icons.activity size={16} />} />
        <Stat label="Completed, 24 h" value={completed} tone={completed ? "success" : undefined} icon={<Icons.checkCircle size={16} />} />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-fg-subtle">
        <span className="flex items-center gap-1.5">
          AI model
          {health ? (
            <Badge tone={health.llm.configured ? "success" : "warning"}>{health.llm.configured ? health.llm.model : "fallback mode"}</Badge>
          ) : <Badge tone="danger">API offline</Badge>}
        </span>
        <span className="flex items-center gap-1.5">
          HMS
          {hms ? <Badge tone={hms.connected ? "success" : "danger"}>{hms.provider} · {hms.connected ? "connected" : "offline"}</Badge> : <Badge>unknown</Badge>}
        </span>
        {hospitalId ? <span>Active clinic <span className="font-mono text-fg-muted">{hospitalId}</span></span> : null}
      </div>
    </div>
  );
}