"use client";

import { useState } from "react";
import { casesApi } from "@/lib/api";
import type { PatientCase, PatientVisitItem } from "@/lib/api";
import { cn, formatDateTime, shortId } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Alert, EmptyState, Skeleton } from "@/components/ui/feedback";
import { Icons } from "@/components/ui/icons";
import { PatientResults } from "@/features/intake/patient-results";

type Loaded = PatientCase | "loading" | "error";

export function VisitsPanel({ currentCaseId, initialVisits }: {
  currentCaseId: string | null;
  initialVisits: PatientVisitItem[];
}) {
  const [visits, setVisits] = useState(initialVisits);
  const [refreshing, setRefreshing] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, Loaded>>({});

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

  async function refresh() {
    setRefreshing(true);
    try {
      setVisits(await casesApi.patientList());
    } finally {
      setRefreshing(false);
    }
  }

  const currentVisit = currentCaseId && !visits.some((visit) => visit.case_id === currentCaseId)
    ? [{ case_id: currentCaseId, status: "CREATED" as const, review_decision: null, department_name: null,
        doctor_name: null, created_at: new Date().toISOString(), updated_at: null }, ...visits]
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
              <li key={visit.case_id} className="overflow-hidden rounded-lg border border-line bg-surface shadow-card">
                <button type="button" aria-expanded={isOpen}
                  onClick={() => (isOpen ? setOpen(null) : void load(visit.case_id))}
                  className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-sunken">
                  <span>
                    <span className="text-sm font-medium">Visit {shortId(visit.case_id)}</span>
                    <span className="ml-2 text-xs text-fg-muted">
                      {visit.case_id === currentCaseId ? "Current conversation" : formatDateTime(visit.created_at)}
                    </span>
                  </span>
                  <Icons.chevronDown size={16} className={cn("text-fg-muted transition-transform", isOpen && "rotate-180")} />
                </button>
                {isOpen ? (
                  <div className="border-t border-line bg-canvas p-4">
                    {!detail || detail === "loading" ? (
                      <div className="space-y-2"><Skeleton className="h-5 w-1/2" /><Skeleton className="h-16 w-full" /></div>
                    ) : detail === "error" ? (
                      <Alert tone="danger" title="Could not load this visit">
                        <Button size="sm" variant="secondary" className="mt-2" onClick={() => void load(visit.case_id)}>Try again</Button>
                      </Alert>
                    ) : (
                      <PatientResults detail={detail} onUpdated={() => void load(visit.case_id)} onRefresh={() => void load(visit.case_id)} />
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
