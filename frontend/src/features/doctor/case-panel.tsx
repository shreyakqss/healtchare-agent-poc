"use client";

import Link from "next/link";
import type { CaseDetail } from "@/lib/api";
import { Avatar, Badge, Button, Icons, Skeleton, StatusBadge } from "@/components/ui";
import { Briefing } from "@/features/doctor/briefing";
import { ConsultationForm } from "@/features/doctor/consultation-form";
import { DiscrepancyFlags } from "@/features/doctor/discrepancy-flags";
import { FinalSummary } from "@/features/doctor/final-summary";
import { PatientRecord } from "@/features/doctor/patient-record";
import { ReviewForm } from "@/features/doctor/review-form";
import { RoutingCard, TriageEvidence } from "@/features/doctor/triage-evidence";
import type { Me } from "@/features/doctor/use-doctor";

export function CasePanelSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading case">
      <Skeleton className="h-14" />
      <Skeleton className="h-56" />
      <Skeleton className="h-40" />
    </div>
  );
}

export function CasePanel({ c, me, onBack, onChanged }: { c: CaseDetail; me: Me; onBack: () => void; onChanged: () => Promise<void> }) {
  const d = c.demographics;
  const meta = [d.age ? `${d.age} y` : null, d.sex].filter(Boolean).join(" · ");
  const review = c.review;

  return (
    <div className="animate-in space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" size="sm" className="lg:hidden" onClick={onBack} icon={<Icons.arrowLeft size={16} />}>Worklist</Button>
        <Avatar name={d.name} size="lg" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold leading-6">{d.name || "Unnamed patient"}</h2>
            <StatusBadge status={c.status} />
            {c.hms_patient_id ? <Badge tone="info"><Icons.link size={12} /> {c.hms_patient_id}</Badge> : null}
          </div>
          <p className="text-sm text-fg-muted">{meta || "Demographics not collected"}{review ? ` · reviewed by ${review.reviewer_id} (${review.decision})` : ""}</p>
        </div>
        <Link href={`/cases/${c.case_id}`} className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line px-3 text-sm font-medium hover:bg-sunken">
          Open full case <Icons.external size={14} />
        </Link>
      </div>

      {c.status === "NEEDS_REVIEW" ? <ReviewForm c={c} me={me} onDone={onChanged} /> : null}
      {c.status === "APPROVED" ? <ConsultationForm c={c} me={me} onDone={onChanged} /> : null}
      {c.status === "COMPLETED" ? <FinalSummary c={c} /> : null}

      <Briefing c={c} />
      <TriageEvidence c={c} />
      <DiscrepancyFlags c={c} />
      <RoutingCard c={c} />
      <PatientRecord c={c} />
    </div>
  );
}