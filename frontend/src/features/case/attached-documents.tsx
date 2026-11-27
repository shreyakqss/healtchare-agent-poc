"use client";

import { casesApi, type CaseDetail, type FileRead } from "@/lib/api";
import { Badge, Card, CardBody, CardHeader, Icons } from "@/components/ui";
import { attachmentKindLabel } from "@/lib/constants";

// Intake sentinels are not medicines the patient named (backend app/domain/intake_fields.py).
const SENTINEL = /^(None reported by patient|Declined to answer|Answered - see the intake transcript|Not asked - intake ended first)$/;

function stem(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9 ]/g, " ").trim().split(/\s+/)[0] ?? "";
}

/** Whether the patient said, during intake, that they take this prescribed medicine. */
function patientTakes(medicine: string, patientMeds: string[]): boolean {
  const key = stem(medicine);
  return key.length > 2 && patientMeds.some((m) => {
    const theirs = stem(m);
    return theirs.length > 2 && (theirs.startsWith(key) || key.startsWith(theirs));
  });
}

/** Overview: every upload in one place, each with its AI summary (for the doctor only) and,
 * for a prescription, which of its medicines the patient confirmed taking. */
export function AttachedDocuments({ detail }: { detail: CaseDetail }) {
  if (!detail.attachments.length) return null;
  const reads = new Map<string, FileRead>(
    ((detail.file_reads?.sections.reads as FileRead[] | undefined) ?? []).map((r) => [r.attachment_id, r]),
  );
  const patientMeds = detail.allergies_medications
    .filter((e) => e.kind === "medication" && !SENTINEL.test(e.name))
    .map((e) => e.name);

  return (
    <Card>
      <CardHeader
        title={<span className="flex items-center gap-2"><Icons.paperclip size={16} className="text-brand" />Attached documents ({detail.attachments.length})</span>}
        description="What the patient uploaded, with an AI summary of each for you only. Open the file to review it yourself."
      />
      <CardBody>
        <ul className="space-y-3">
          {detail.attachments.map((a) => {
            const read = reads.get(a.id);
            const meds = a.extracted_medications ?? [];
            return (
              <li key={a.id} className="rounded-md border border-line p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-fg-muted">{a.mime_type.startsWith("image/") ? <Icons.image size={16} /> : <Icons.file size={16} />}</span>
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">{a.filename}</span>
                  <Badge>{attachmentKindLabel(a.kind)}</Badge>
                  <a href={casesApi.fileUrl(detail.case_id, a.id)} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:underline">
                    Open <Icons.external size={12} />
                  </a>
                </div>
                {read?.status === "read" ? (
                  <div className="mt-2 space-y-1 text-sm">
                    <p className="flex items-center gap-1.5 text-xs text-fg-subtle"><Icons.sparkles size={12} />{read.label ?? "AI read, not a radiology report"}</p>
                    {read.what_it_is ? <p className="font-medium">{read.what_it_is}</p> : null}
                    {read.impression ? <p className="text-fg">{read.impression}</p> : null}
                    {read.findings?.length ? (
                      <ul className="list-disc space-y-0.5 pl-5 text-fg-muted">
                        {read.findings.slice(0, 5).map((f, i) => <li key={i}>{f}</li>)}
                        {read.findings.length > 5 ? <li className="list-none text-xs text-fg-subtle">+{read.findings.length - 5} more in Facts &amp; records</li> : null}
                      </ul>
                    ) : null}
                  </div>
                ) : (
                  <p className="mt-2 text-xs text-fg-subtle">
                    {read?.note ?? (read ? "The AI could not read this file." : "Not summarised yet (pre-screening reads uploads).")} Open it to review.
                  </p>
                )}
                {meds.length ? (
                  <div className="mt-2.5 border-t border-line pt-2.5">
                    <p className="text-xs font-medium text-fg-muted">Medicines on this prescription</p>
                    <ul className="mt-1.5 flex flex-wrap gap-1.5">
                      {meds.map((m) => {
                        const takes = patientTakes(m, patientMeds);
                        return (
                          <li key={m}>
                            <Badge tone={takes ? "success" : "warning"}>
                              {m} · {takes ? "patient takes it" : "not confirmed by patient"}
                            </Badge>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      </CardBody>
    </Card>
  );
}
