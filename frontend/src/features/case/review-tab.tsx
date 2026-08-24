import type { CaseDetail } from "@/lib/api";
import { Card, CardBody, CardHeader, SectionTitle } from "@/components/ui/card";
import { Badge, PriorityBadge } from "@/components/ui/badge";
import { Alert, EmptyState } from "@/components/ui/feedback";
import { KeyValue } from "@/components/ui/data";
import { Icons } from "@/components/ui/icons";
import { formatDateTime, titleCase } from "@/lib/utils";

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v : null;
}
function list(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}
function original(sections: Record<string, unknown>, key: string): string {
  const v = sections[key];
  if (Array.isArray(v)) return v.join(", ");
  return str(v) ?? "–";
}

export function ReviewTab({ detail }: { detail: CaseDetail }) {
  const review = detail.review;
  const sections = (detail.prescreening_summary?.sections ?? {}) as Record<string, unknown>;
  const fin = (detail.final_summary?.sections ?? {}) as Record<string, unknown>;
  const decisionTone = review?.decision === "reject" ? "danger" : review?.decision === "edit" ? "warning" : "success";

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader title="Clinician review" description="The gate: consultation notes and the visit summary are only possible after approve or approve-with-edits." />
        <CardBody>
          {!review ? (
            <EmptyState icon={<Icons.shield size={20} />} title="Not reviewed yet" description={detail.status === "NEEDS_REVIEW" ? "Awaiting a clinician." : "Pre-screening must finish before a review can be recorded."} />
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={decisionTone}>{titleCase(review.decision)}</Badge>
                <span className="text-sm">by <span className="font-medium">{review.reviewer_id}</span> ({review.reviewer_role})</span>
                <span className="text-xs text-fg-subtle" suppressHydrationWarning>{formatDateTime(review.created_at)}</span>
              </div>
              {review.comment ? <p className="rounded-md bg-sunken p-3 text-sm leading-6">{review.comment}</p> : null}
              {Object.keys(review.edits).length ? (
                <div>
                  <SectionTitle className="mb-2">Edits (kept apart from the patient&rsquo;s statements)</SectionTitle>
                  <ul className="divide-y divide-line rounded-md border border-line">
                    {Object.entries(review.edits).map(([k, v]) => (
                      <li key={k} className="grid gap-2 p-3 sm:grid-cols-[10rem_1fr_1fr]">
                        <span className="text-sm font-medium">{titleCase(k)}</span>
                        <div><p className="text-[11px] uppercase tracking-wider text-fg-subtle">Original</p><p className="text-sm text-fg-muted line-through">{original(sections, k)}</p></div>
                        <div><p className="text-[11px] uppercase tracking-wider text-fg-subtle">Clinician</p><p className="text-sm">{String(v)}</p></div>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Consultation notes" description="Authored by the clinician; no agent writes here." />
        <CardBody>
          {!detail.consultation_notes.length ? (
            <EmptyState icon={<Icons.stethoscope size={20} />} title="No consultation recorded" />
          ) : (
            <ul className="space-y-4">
              {detail.consultation_notes.map((n) => (
                <li key={n.id} className="rounded-md border border-line p-4">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-medium">{n.doctor_name ?? n.doctor_id}</span>
                    <Badge tone="info">{n.consultation_mode === "virtual" ? <Icons.video size={12} /> : <Icons.mapPin size={12} />} {titleCase(n.consultation_mode)}</Badge>
                    <span className="text-xs text-fg-subtle" suppressHydrationWarning>{formatDateTime(n.created_at)}</span>
                  </div>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-6">{n.notes}</p>
                  <KeyValue className="mt-3" columns={2} items={[
                    { label: "Prescription", value: n.prescription ?? <span className="text-fg-subtle">None</span> },
                    { label: "Follow-up", value: n.follow_up_instructions ?? <span className="text-fg-subtle">None</span> },
                  ]} />
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Final visit summary" action={detail.final_summary ? <Badge tone={detail.final_summary.generated_by === "llm" ? "brand" : "neutral"}>{detail.final_summary.generated_by === "llm" ? "AI draft" : "Assembled from notes"}</Badge> : null} />
        <CardBody>
          {!detail.final_summary ? (
            <EmptyState title="Not released yet" description="Generated when the clinician finalises the visit." />
          ) : (
            <div className="space-y-4">
              <KeyValue columns={2} items={[
                { label: "Visit reason", value: str(fin.visit_reason) },
                { label: "Department / doctor", value: [str(fin.department), str(fin.doctor)].filter(Boolean).join(" · ") || "–" },
              ]} />
              {str(fin.consultation_overview) ? <div><SectionTitle>Overview</SectionTitle><p className="mt-1 text-sm leading-6">{str(fin.consultation_overview)}</p></div> : null}
              {str(fin.doctor_notes_summary) ? <div><SectionTitle>Doctor&rsquo;s notes</SectionTitle><p className="mt-1 text-sm leading-6">{str(fin.doctor_notes_summary)}</p></div> : null}
              {list(fin.follow_up_instructions).length ? <div><SectionTitle>Follow-up</SectionTitle><ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">{list(fin.follow_up_instructions).map((x, i) => <li key={i}>{x}</li>)}</ul></div> : null}
              {str(fin.prescription) ? <div><SectionTitle>Prescription</SectionTitle><p className="mt-1 text-sm">{str(fin.prescription)}</p></div> : null}
              {str(fin.patient_friendly_summary) ? <Alert tone="success" title="Patient-facing summary">{str(fin.patient_friendly_summary)}</Alert> : null}
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Care tasks" description="Drafts only. An appointment request to the HMS, never a confirmed booking." />
        <CardBody>
          {!detail.care_tasks.length ? (
            <EmptyState icon={<Icons.calendar size={20} />} title="No task drafted" />
          ) : (
            <ul className="space-y-3">
              {detail.care_tasks.map((t) => {
                const p = t.payload as Record<string, unknown>;
                const slot = p.slot as { start?: string; practitioner_id?: string } | null | undefined;
                return (
                  <li key={t.id} className="rounded-md border border-line p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">{titleCase(t.task_type)}</span>
                      <Badge tone="warning">{titleCase(t.status)}</Badge>
                      <PriorityBadge priority={t.priority} />
                      {t.hms_reference ? <Badge tone="info"><Icons.link size={12} /> {t.hms_reference}</Badge> : null}
                    </div>
                    <KeyValue className="mt-3" columns={3} items={[
                      { label: "Department", value: str(p.department) },
                      { label: "Doctor", value: str(p.doctor) },
                      { label: "Requested slot", value: slot?.start ? <span suppressHydrationWarning>{formatDateTime(slot.start)}</span> : <span className="text-fg-subtle">None</span> },
                    ]} />
                    {t.notes ? <p className="mt-3 text-sm text-fg-muted">{t.notes}</p> : null}
                  </li>
                );
              })}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}