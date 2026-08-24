"use client";

import { useState } from "react";
import type { CaseListItem } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import { Button, EmptyState, Icons, Input, PriorityBadge } from "@/components/ui";
import type { Me } from "@/features/doctor/use-doctor";

export type Bucket = "review" | "consult" | "completed" | "other";

export function bucketOf(c: CaseListItem): Bucket {
  if (c.status === "NEEDS_REVIEW") return "review";
  if (c.status === "APPROVED") return "consult";
  if (c.status === "COMPLETED") return "completed";
  return "other";
}

export function isMine(c: CaseListItem, me: Me): boolean {
  return c.doctor_id === me.id || (c.department_id === me.department_id && !c.doctor_id);
}

const SECTIONS: Array<{ id: Bucket; label: string; collapsed?: boolean }> = [
  { id: "review", label: "Awaiting your review" },
  { id: "consult", label: "Ready to consult" },
  { id: "completed", label: "Completed" },
  { id: "other", label: "Other", collapsed: true },
];

export function Worklist({ cases, me, selectedId, onSelect, onRefresh, refreshing, now }: {
  cases: CaseListItem[]; me: Me; selectedId: string | null; onSelect: (id: string) => void;
  onRefresh: () => void; refreshing: boolean; now: number;
}) {
  const [q, setQ] = useState("");
  const [openOther, setOpenOther] = useState(false);
  const mine = cases.filter((c) => isMine(c, me));
  const needle = q.trim().toLowerCase();
  const filtered = needle
    ? mine.filter((c) => `${c.demographics.name ?? ""} ${c.chief_complaint ?? ""}`.toLowerCase().includes(needle))
    : mine;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 pb-3">
        <div className="relative flex-1">
          <Icons.search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-subtle" />
          <Input aria-label="Search your cases" placeholder="Search patient or complaint" value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" />
        </div>
        <Button variant="secondary" size="md" onClick={onRefresh} loading={refreshing} icon={<Icons.refresh size={16} />} aria-label="Refresh worklist">
          <span className="sr-only sm:not-sr-only">Refresh</span>
        </Button>
      </div>

      {mine.length === 0 ? (
        <EmptyState icon={<Icons.list size={20} />} title="Nothing assigned to you" description={`No cases routed to you or to ${me.department_name} right now.`} />
      ) : null}

      <div className="scrollbar-thin flex-1 space-y-4 overflow-y-auto pr-1">
        {SECTIONS.map((s) => {
          const rows = filtered.filter((c) => bucketOf(c) === s.id);
          if (!rows.length) return null;
          const collapsed = s.collapsed && !openOther;
          return (
            <section key={s.id} aria-label={s.label}>
              <button
                type="button"
                onClick={() => s.collapsed && setOpenOther((v) => !v)}
                className={cn("mb-1.5 flex w-full items-center justify-between px-1 text-xs font-semibold uppercase tracking-wider text-fg-subtle", s.collapsed && "hover:text-fg")}
                aria-expanded={s.collapsed ? !collapsed : undefined}
              >
                <span>{s.label}</span>
                <span className="tabular flex items-center gap-1">{rows.length}{s.collapsed ? <Icons.chevronDown size={14} className={cn("transition-transform", !collapsed && "rotate-180")} /> : null}</span>
              </button>
              {!collapsed ? (
                <ul className="space-y-1">
                  {rows.map((c) => <Row key={c.case_id} c={c} active={c.case_id === selectedId} onSelect={onSelect} now={now} />)}
                </ul>
              ) : null}
            </section>
          );
        })}
      </div>
    </div>
  );
}

function Row({ c, active, onSelect, now }: { c: CaseListItem; active: boolean; onSelect: (id: string) => void; now: number }) {
  const who = c.demographics.name || "Unnamed patient";
  const meta = [c.demographics.age ? `${c.demographics.age} y` : null, c.demographics.sex].filter(Boolean).join(" · ");
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(c.case_id)}
        aria-current={active ? "true" : undefined}
        className={cn(
          "w-full rounded-md border px-3 py-2.5 text-left transition-colors",
          active ? "border-brand-ring bg-brand-soft/50" : "border-transparent hover:bg-sunken",
        )}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-1.5 text-sm font-medium">
            <span className="truncate">{who}</span>
            {c.hms_patient_id ? <Icons.link size={13} className="shrink-0 text-fg-subtle" aria-label="Linked hospital record" /> : null}
          </span>
          <PriorityBadge priority={c.priority} />
        </div>
        <p className="mt-0.5 truncate text-[13px] text-fg-muted">{c.chief_complaint ?? "No complaint recorded"}</p>
        <p className="mt-1 flex items-center gap-2 text-[11px] text-fg-subtle">
          {meta ? <span>{meta}</span> : null}
          <span className="tabular ml-auto">{timeAgo(c.updated_at ?? c.created_at, now)}</span>
        </p>
      </button>
    </li>
  );
}