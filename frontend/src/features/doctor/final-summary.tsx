"use client";

import type { CaseDetail } from "@/lib/api";
import { formatDateTime, titleCase } from "@/lib/utils";
import { Alert, Badge, Card, CardBody, CardHeader, KeyValue, SectionTitle } from "@/components/ui";

interface FinalSections {
  visit_reason?: string; consultation_overview?: string; doctor_notes_summary?: string;
  follow_up_instructions?: string[]; patient_friendly_summary?: string; prescription?: string | null;
}

export function FinalSummary({ c }: { c: CaseDetail }) {
  const s = c.final_summary;
  const task = c.care_tasks[c.care_tasks.length - 1];
  if (!s) return null;
  const f = s.sections as FinalSections;
  const slot = (task?.payload as { slot?: { start?: string } | null } | undefined)?.slot;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title="Visit summary" description={`Released ${formatDateTime(s.created_at)}`}
          action={<Badge tone={s.generated_by === "llm" ? "brand" : "neutral"}>{s.generated_by === "llm" ? "AI draft from your notes" : "Plain copy of your notes"}</Badge>} />
        <CardBody className="space-y-5">
          <KeyValue columns={2} items={[{ label: "Visit reason", value: f.visit_reason }, { label: "Consultation", value: f.consultation_overview }]} />
          <div><SectionTitle>Notes summary</SectionTitle><p className="mt-1.5 text-sm leading-6">{f.doctor_notes_summary}</p></div>
          {f.prescription ? <div><SectionTitle>Prescription</SectionTitle><p className="mt-1.5 text-sm">{f.prescription}</p></div> : null}
          {f.follow_up_instructions?.length ? (
            <div><SectionTitle>Follow-up</SectionTitle><ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm">{f.follow_up_instructions.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
          ) : null}
          {f.patient_friendly_summary ? (
            <div className="rounded-md bg-brand-soft/60 px-3.5 py-3">
              <SectionTitle className="text-brand">What the patient sees</SectionTitle>
              <p className="mt-1.5 text-sm leading-6">{f.patient_friendly_summary}</p>
            </div>
          ) : null}
        </CardBody>
      </Card>

      {task ? (
        <Card>
          <CardHeader title="Care task" action={<Badge tone="warning">{task.status}</Badge>} />
          <CardBody className="space-y-3">
            <KeyValue columns={2} items={[
              { label: "Type", value: titleCase(task.task_type) },
              { label: "HMS reference", value: task.hms_reference ? <code className="font-mono text-xs">{task.hms_reference}</code> : "–" },
              { label: "Department", value: String(task.payload.department ?? "–") },
              { label: "Proposed slot", value: slot?.start ? formatDateTime(slot.start) : "–" },
            ]} />
            {task.notes ? <p className="text-sm text-fg-muted">{task.notes}</p> : null}
            <Alert tone="info">This is a draft request sent to the hospital system. It is not a confirmed booking, scheduling staff confirm it.</Alert>
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}