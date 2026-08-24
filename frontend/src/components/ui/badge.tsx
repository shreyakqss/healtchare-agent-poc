import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { PRIORITY_LABEL, STATUS_LABEL } from "@/lib/constants";
import type { CaseStatus, Priority } from "@/lib/api/types";

export type Tone = "neutral" | "brand" | "danger" | "warning" | "success" | "info";

const tones: Record<Tone, string> = {
  neutral: "bg-neutral-soft text-fg-muted border-line",
  brand: "bg-brand-soft text-brand border-transparent",
  danger: "bg-danger-soft text-danger border-transparent",
  warning: "bg-warning-soft text-warning border-transparent",
  success: "bg-success-soft text-success border-transparent",
  info: "bg-info-soft text-info border-transparent",
};

export function Badge({ tone = "neutral", children, className, dot }: { tone?: Tone; children: ReactNode; className?: string; dot?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap", tones[tone], className)}>
      {dot ? <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

export const PRIORITY_TONE: Record<Priority, Tone> = { high: "danger", medium: "warning", low: "success" };

export function PriorityBadge({ priority, className }: { priority: Priority | null | undefined; className?: string }) {
  if (!priority) return <Badge className={className}>Not triaged</Badge>;
  return (
    <Badge tone={PRIORITY_TONE[priority]} dot className={className}>
      {PRIORITY_LABEL[priority]}
    </Badge>
  );
}

export const STATUS_TONE: Record<CaseStatus, Tone> = {
  CREATED: "neutral", INGESTING: "info", ANALYZING: "info", NEEDS_REVIEW: "warning",
  APPROVED: "brand", COMPLETED: "success", REJECTED: "neutral", FAILED: "danger",
};

export function StatusBadge({ status, className }: { status: CaseStatus; className?: string }) {
  return <Badge tone={STATUS_TONE[status]} className={className}>{STATUS_LABEL[status] ?? status}</Badge>;
}