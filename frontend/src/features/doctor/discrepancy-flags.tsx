"use client";

import type { CaseDetail } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { Badge, Card, CardBody, CardHeader, EmptyState, Icons } from "@/components/ui";

/** Clinician-facing only. Patient said X vs document/HMS says Y - never rendered under
 * features/intake or patient-results.tsx, and never fed into triage_engine.evaluate(). */
export function DiscrepancyFlags({ c }: { c: CaseDetail }) {
  const items = c.discrepancies;

  if (!items.length) {
    return (
      <Card>
        <CardHeader title="Discrepancies" description="Patient statements checked against uploaded documents and HMS records." />
        <CardBody>
          <EmptyState icon={<Icons.checkCircle size={18} />} title="No discrepancies flagged" />
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Discrepancies"
        description="Patient statements checked against uploaded documents and HMS records. Advisory only - not used for triage."
        action={<Badge tone="warning">{items.length} flagged</Badge>}
      />
      <CardBody className="space-y-3">
        {items.map((d) => (
          <div key={d.id} className="rounded-md border border-line bg-sunken/60 px-3.5 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-fg">{d.field_or_topic}</span>
              <Badge tone="warning">{d.severity === "review" ? "Needs review" : "Info"}</Badge>
              <Badge>{d.source_kind === "hms" ? "HMS record" : "Document"}</Badge>
            </div>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <div className="rounded-md bg-surface px-3 py-2">
                <p className="text-[11px] font-medium uppercase tracking-wide text-fg-subtle">Patient said</p>
                <p className="mt-0.5 text-sm text-fg">{d.patient_stated}</p>
              </div>
              <div className="rounded-md bg-surface px-3 py-2">
                <p className="text-[11px] font-medium uppercase tracking-wide text-fg-subtle">
                  {d.source_kind === "hms" ? "HMS says" : "Document says"}
                </p>
                <p className="mt-0.5 text-sm text-fg">{d.document_says}</p>
              </div>
            </div>
            {d.requested_document_kind ? (
              <p className="mt-2 text-[13px] text-fg-muted">
                Consider requesting: <span className="font-medium text-fg">{d.requested_document_kind}</span> from the patient.
              </p>
            ) : null}
          </div>
        ))}
        <p className="text-xs text-fg-subtle">Last checked {formatDateTime(items[items.length - 1].created_at)}.</p>
      </CardBody>
    </Card>
  );
}
