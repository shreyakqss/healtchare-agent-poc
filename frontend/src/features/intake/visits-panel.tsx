"use client";

import { useState } from "react";
import { casesApi } from "@/lib/api";
import type { PatientCase, PatientVisitItem, PreviousVisit, VisitType } from "@/lib/api";
import { cn, formatDate, formatDateTime } from "@/lib/utils";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert, EmptyState, Skeleton, useToast } from "@/components/ui/feedback";
import { Icons } from "@/components/ui/icons";
import { PatientResults } from "@/features/intake/patient-results";

type Loaded = PatientCase | "loading" | "error";

// Where the visit stands, in the patient's terms (never priority or review internals).
const STAGE: Partial<Record<PatientVisitItem["status"], { label: string; tone: Tone }>> = {
  CREATED: { label: "In progress", tone: "info" },
  INGESTING: { label: "In progress", tone: "info" },
  ANALYZING: { label: "Being prepared", tone: "info" },
  NEEDS_REVIEW: { label: "Upcoming", tone: "brand" },
  APPROVED: { label: "Upcoming", tone: "brand" },
  COMPLETED: { label: "Completed", tone: "success" },
  FAILED: { label: "Needs attention", tone: "warning" },
};

export function VisitsPanel({ currentCaseId, currentVisitType = "new", currentPrevious = null, initialVisits }: {
  currentCaseId: string | null;
  // The visit started in this page session, until the list next includes it.
  currentVisitType?: VisitType;
  currentPrevious?: PreviousVisit | null;
  initialVisits: PatientVisitItem[];
}) {
  const [visits, setVisits] = useState(initialVisits);
  const [refreshing, setRefreshing] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, Loaded>>({});
  const [checking, setChecking] = useState<string | null>(null);
  const toast = useToast();

  async function load(caseId: string) {
    setOpen(caseId);
    setDetails((current) => ({ ...current, [caseId]: "loading" }));
    try {
      const detail = await casesApi.patientGet(caseId);
      setDetails((current) => ({ ...current, [caseId]: detail }));
    } catch {
      setDetails((current) => ({ ...current, [caseId]: "error" }));
    }
  }

  // Re-fetch one open visit in place: the loaded card stays up (no skeleton flash) and a failure
  // keeps what was there. Returns false so callers can say so.
  async function reloadDetail(caseId: string): Promise<boolean> {
    try {
      const detail = await casesApi.patientGet(caseId);
      setDetails((current) => ({ ...current, [caseId]: detail }));
      return true;
    } catch {
      return false;
    }
  }

  async function checkVisit(caseId: string) {
    setChecking(caseId);
    try {
      if (!(await reloadDetail(caseId))) toast.push({ tone: "danger", message: "Could not check for updates. Please try again." });
    } finally {
      setChecking(null);
    }
  }

  // The list alone never changes what an open visit shows (status, appointment times), so
  // refresh the open one too.
  async function refresh() {
    setRefreshing(true);
    try {
      const [list, detailOk] = await Promise.all([
        casesApi.patientList(),
        open ? reloadDetail(open) : Promise.resolve(true),
      ]);
      setVisits(list);
      toast.push(detailOk
        ? { tone: "success", message: "Your visits are up to date." }
        : { tone: "danger", message: "Could not refresh the open visit. Please try again." });
    } catch {
      toast.push({ tone: "danger", message: "Could not refresh your visits. Please try again." });
    } finally {
      setRefreshing(false);
    }
  }

  const currentVisit = currentCaseId && !visits.some((visit) => visit.case_id === currentCaseId)
    ? [{ case_id: currentCaseId, status: "CREATED" as const, review_decision: null, department_name: null,
        doctor_name: null, created_at: new Date().toISOString(), updated_at: null, visit_type: currentVisitType,
        follow_up_of: currentPrevious?.case_id ?? null,
        follow_up_title: currentPrevious?.diagnosis?.split("\n")[0]?.trim() || currentPrevious?.complaint || null,
        follow_up_at: currentPrevious?.visit_at ?? null }, ...visits]
    : visits;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs leading-5 text-fg-subtle">Visits are linked to your signed-in patient account.</p>
        <Button variant="ghost" size="sm" loading={refreshing} icon={<Icons.refresh size={14} />} onClick={() => void refresh()}>Refresh</Button>
      </div>
      {currentVisit.length ? (
        <ul className="space-y-3">
          {currentVisit.map((visit) => {
            const detail = details[visit.case_id];
            const isOpen = open === visit.case_id;
            return (
              <li key={visit.case_id} className={cn(
                "overflow-hidden rounded-lg border border-line bg-surface shadow-card",
                visit.visit_type === "follow_up" && "border-l-4 border-l-brand",
              )}>
                <VisitHeader visit={visit} current={visit.case_id === currentCaseId} open={isOpen}
                  onToggle={() => (isOpen ? setOpen(null) : void load(visit.case_id))} />
                {isOpen ? (
                  <div className="border-t border-line bg-canvas p-4">
                    {!detail || detail === "loading" ? (
                      <div className="space-y-2"><Skeleton className="h-5 w-1/2" /><Skeleton className="h-16 w-full" /></div>
                    ) : detail === "error" ? (
                      <Alert tone="danger" title="Could not load this visit">
                        <Button size="sm" variant="secondary" className="mt-2" onClick={() => void load(visit.case_id)}>Try again</Button>
                      </Alert>
                    ) : (
                      <PatientResults
                        detail={detail}
                        onUpdated={(updated) => setDetails((current) => ({ ...current, [visit.case_id]: updated }))}
                        onRefresh={() => void checkVisit(visit.case_id)}
                        refreshing={checking === visit.case_id}
                      />
                    )}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <EmptyState icon={<Icons.calendar size={20} />} title="No visits yet" description="Start a conversation with the assistant and it will appear here." />
      )}
    </div>
  );
}

function VisitHeader({ visit, current, open, onToggle }: {
  visit: PatientVisitItem; current: boolean; open: boolean; onToggle: () => void;
}) {
  const followUp = visit.visit_type === "follow_up";
  const stage = STAGE[visit.status];
  const where = [visit.department_name, visit.doctor_name].filter(Boolean).join(" · ");
  return (
    <button type="button" aria-expanded={open} onClick={onToggle}
      className="flex w-full items-start justify-between gap-3 px-4 py-3.5 text-left hover:bg-sunken">
      <span className="min-w-0 space-y-1">
        <span className="flex flex-wrap items-center gap-2">
          <Badge tone={followUp ? "brand" : "neutral"}>
            {followUp ? <><Icons.refresh size={11} /> Follow-up</> : <><Icons.plus size={11} /> New visit</>}
          </Badge>
          {current ? <Badge tone="info" dot>Current</Badge> : stage ? <Badge tone={stage.tone}>{stage.label}</Badge> : null}
        </span>
        <span className="block truncate text-sm font-semibold">
          {visit.complaint ?? (current ? "Visit in progress" : "Visit")}
        </span>
        {followUp && visit.follow_up_title ? (
          <span className="block text-xs text-fg-muted">
            Follow-up to <span className="font-medium text-fg">{visit.follow_up_title}</span>
            {visit.follow_up_at ? ` (${formatDate(visit.follow_up_at)})` : ""}
          </span>
        ) : null}
        <span className="block text-xs text-fg-subtle">
          {[where, current ? null : formatDateTime(visit.created_at)].filter(Boolean).join(" · ") || "Not booked yet"}
        </span>
      </span>
      <Icons.chevronDown size={16} className={cn("mt-1 shrink-0 text-fg-muted transition-transform", open && "rotate-180")} />
    </button>
  );
}
