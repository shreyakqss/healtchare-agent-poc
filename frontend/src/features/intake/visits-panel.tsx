"use client";

import { useState } from "react";
import { casesApi } from "@/lib/api";
import type { CaseDetail } from "@/lib/api";
import { listVisits, type VisitRef } from "@/lib/patient-history";
import { cn, formatDateTime, shortId } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Alert, EmptyState, Skeleton } from "@/components/ui/feedback";
import { Icons } from "@/components/ui/icons";
import { PatientResults } from "@/features/intake/patient-results";

type Loaded = CaseDetail | "loading" | "error";

export function VisitsPanel({ currentCaseId }: { currentCaseId: string | null }) {
  const [visits, setVisits] = useState<VisitRef[]>(() => listVisits());
  const [open, setOpen] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, Loaded>>({});

  async function load(caseId: string) {
    setOpen(caseId);
    setDetails((d) => ({ ...d, [caseId]: "loading" }));
    try {
      const detail = await casesApi.get(caseId);
      setDetails((d) => ({ ...d, [caseId]: detail }));
    } catch {
      setDetails((d) => ({ ...d, [caseId]: "error" }));
    }
  }

  const all = currentCaseId && !visits.some((v) => v.caseId === currentCaseId)
    ? [{ caseId: currentCaseId, createdAt: "" }, ...visits]
    : visits;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs leading-5 text-fg-subtle">There is no patient account in this proof of concept, so your visits are remembered only in this browser.</p>
        <Button variant="ghost" size="sm" icon={<Icons.refresh size={14} />} onClick={() => setVisits(listVisits())}>Refresh</Button>
      </div>
      {all.length ? (
        <ul className="space-y-3">
          {all.map((v) => {
            const d = details[v.caseId];
            const isOpen = open === v.caseId;
            return (
              <li key={v.caseId} className="overflow-hidden rounded-lg border border-line bg-surface shadow-card">
                <button type="button" aria-expanded={isOpen}
                  onClick={() => (isOpen ? setOpen(null) : void load(v.caseId))}
                  className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-sunken">
                  <span>
                    <span className="text-sm font-medium">Visit {shortId(v.caseId)}</span>
                    <span className="ml-2 text-xs text-fg-muted">{v.caseId === currentCaseId ? "Current conversation" : formatDateTime(v.createdAt)}</span>
                  </span>
                  <Icons.chevronDown size={16} className={cn("text-fg-muted transition-transform", isOpen && "rotate-180")} />
                </button>
                {isOpen ? (
                  <div className="border-t border-line bg-canvas p-4">
                    {!d || d === "loading" ? (
                      <div className="space-y-2"><Skeleton className="h-5 w-1/2" /><Skeleton className="h-16 w-full" /></div>
                    ) : d === "error" ? (
                      <Alert tone="danger" title="Could not load this visit">
                        <Button size="sm" variant="secondary" className="mt-2" onClick={() => void load(v.caseId)}>Try again</Button>
                      </Alert>
                    ) : (
                      <>
                        <PatientResults detail={d} />
                        <div className="mt-3 flex justify-end">
                          <Button size="sm" variant="ghost" icon={<Icons.refresh size={14} />} onClick={() => void load(v.caseId)}>Check for updates</Button>
                        </div>
                      </>
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