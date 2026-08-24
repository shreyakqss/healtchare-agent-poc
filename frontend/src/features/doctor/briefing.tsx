"use client";

import type { CaseDetail } from "@/lib/api";
import { FIELD_LABEL } from "@/lib/constants";
import { Alert, Badge, Card, CardBody, CardHeader, EmptyState, Icons, SectionTitle } from "@/components/ui";

export interface BriefingSections {
  chief_complaint?: string;
  reported_symptoms?: string[];
  relevant_history?: string[];
  medications?: string[];
  allergies?: string[];
  context_for_clinician?: string;
  missing_information?: string[];
}

export function briefingOf(c: CaseDetail): BriefingSections {
  return (c.prescreening_summary?.sections ?? {}) as BriefingSections;
}

function List({ items }: { items?: string[] }) {
  if (!items?.length) return <p className="text-sm text-fg-subtle">None recorded</p>;
  return (
    <ul className="space-y-1 text-sm">
      {items.map((x, i) => <li key={i} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-fg-subtle" aria-hidden="true" />{x}</li>)}
    </ul>
  );
}

export function Briefing({ c }: { c: CaseDetail }) {
  const s = c.prescreening_summary;
  if (!s) {
    return (
      <Card>
        <CardHeader title="Clinician briefing" />
        <EmptyState icon={<Icons.file size={18} />} title="No briefing yet" description="Pre-screening has not run for this case." />
      </Card>
    );
  }
  const b = s.sections as BriefingSections;
  return (
    <Card>
      <CardHeader
        title="Clinician briefing"
        description="Summarises what the patient stated. It never diagnoses or judges urgency."
        action={<Badge tone={s.generated_by === "llm" ? "brand" : "neutral"}>{s.generated_by === "llm" ? "AI draft" : "Plain listing"}</Badge>}
      />
      <CardBody className="space-y-5">
        {c.missing_fields.length ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-fg-muted">Not collected:</span>
            {c.missing_fields.map((f) => <Badge key={f} tone="warning">{FIELD_LABEL[f] ?? f}</Badge>)}
          </div>
        ) : null}
        <div>
          <SectionTitle>Chief complaint</SectionTitle>
          <p className="mt-1 text-[15px] font-medium">{b.chief_complaint || "Not recorded"}</p>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <div><SectionTitle>Reported symptoms</SectionTitle><div className="mt-1.5"><List items={b.reported_symptoms} /></div></div>
          <div><SectionTitle>Relevant history</SectionTitle><div className="mt-1.5"><List items={b.relevant_history} /></div></div>
          <div><SectionTitle>Medications</SectionTitle><div className="mt-1.5"><List items={b.medications} /></div></div>
          <div><SectionTitle>Allergies</SectionTitle><div className="mt-1.5"><List items={b.allergies} /></div></div>
        </div>
        {b.context_for_clinician ? (
          <div>
            <SectionTitle>Context</SectionTitle>
            <p className="mt-1.5 text-sm leading-6 text-fg">{b.context_for_clinician}</p>
          </div>
        ) : null}
        {s.missing_information.length ? (
          <Alert tone="warning" title="Missing information">
            <ul className="list-disc pl-4">{s.missing_information.map((m, i) => <li key={i}>{m}</li>)}</ul>
          </Alert>
        ) : null}
      </CardBody>
    </Card>
  );
}