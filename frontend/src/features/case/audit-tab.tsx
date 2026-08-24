"use client";

import { useState } from "react";
import type { AuditEvent } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/feedback";
import { Icons } from "@/components/ui/icons";
import { cn, formatDateTime } from "@/lib/utils";
import { actorLabel, describeEvent, isSystemActor } from "@/features/case/audit-labels";

type Filter = "all" | "system" | "people";

function Row({ e }: { e: AuditEvent }) {
  const [open, setOpen] = useState(false);
  const system = isSystemActor(e.actor);
  const failed = e.action === "workflow.failed";
  const hasPayload = Object.keys(e.payload ?? {}).length > 0;
  return (
    <li className="relative pl-8">
      <span className={cn(
        "absolute left-0 top-1.5 flex h-5 w-5 items-center justify-center rounded-full border-2 border-surface",
        failed ? "bg-danger text-white" : system ? "bg-sunken text-fg-muted" : "bg-brand text-brand-fg",
      )} aria-hidden="true">
        {failed ? <Icons.alert size={11} /> : system ? <Icons.bot size={11} /> : <Icons.user size={11} />}
      </span>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
        <span className="text-sm font-medium">{actorLabel(e.actor)}</span>
        <time dateTime={e.created_at} suppressHydrationWarning className="tabular text-xs text-fg-subtle">{formatDateTime(e.created_at, { timeStyle: "medium" })}</time>
      </div>
      <p className={cn("mt-0.5 text-sm leading-6", failed ? "text-danger" : "text-fg")}>{describeEvent(e)}</p>
      {hasPayload ? (
        <>
          <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="mt-1 inline-flex h-7 items-center gap-1 rounded-sm px-1.5 font-mono text-[11px] text-fg-subtle hover:bg-sunken hover:text-fg">
            <Icons.chevronRight size={12} className={cn("transition-transform", open && "rotate-90")} /> {e.action}
          </button>
          {open ? <pre className="mt-1 overflow-x-auto rounded-md bg-sunken p-3 font-mono text-[11px] leading-5">{JSON.stringify(e.payload, null, 2)}</pre> : null}
        </>
      ) : (
        <p className="mt-1 font-mono text-[11px] text-fg-subtle">{e.action}</p>
      )}
    </li>
  );
}

export function AuditTab({ events }: { events: AuditEvent[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const sorted = [...events].sort((a, b) => a.created_at.localeCompare(b.created_at));
  const shown = sorted.filter((e) => filter === "all" || (filter === "system" ? isSystemActor(e.actor) : !isSystemActor(e.actor)));

  const chips: Array<{ id: Filter; label: string; n: number }> = [
    { id: "all", label: "All", n: sorted.length },
    { id: "system", label: "System", n: sorted.filter((e) => isSystemActor(e.actor)).length },
    { id: "people", label: "People", n: sorted.filter((e) => !isSystemActor(e.actor)).length },
  ];

  return (
    <Card>
      <CardHeader
        title="Audit trail"
        description="Every state change, agent step and human decision, in order."
        action={
          <div role="group" aria-label="Filter events" className="flex gap-1">
            {chips.map((c) => (
              <button key={c.id} type="button" onClick={() => setFilter(c.id)} aria-pressed={filter === c.id}
                className={cn("h-8 rounded-full border px-3 text-xs font-medium transition-colors",
                  filter === c.id ? "border-brand bg-brand-soft text-brand" : "border-line text-fg-muted hover:bg-sunken")}>
                {c.label} <span className="tabular opacity-70">{c.n}</span>
              </button>
            ))}
          </div>
        }
      />
      <CardBody>
        {!shown.length ? (
          <EmptyState icon={<Icons.list size={20} />} title="No events" description={events.length ? "Nothing matches this filter." : "The audit trail is empty or could not be loaded."} />
        ) : (
          <ol className="relative space-y-5 before:absolute before:bottom-2 before:left-[9px] before:top-2 before:w-px before:bg-line">
            {shown.map((e) => <Row key={e.id} e={e} />)}
          </ol>
        )}
      </CardBody>
    </Card>
  );
}