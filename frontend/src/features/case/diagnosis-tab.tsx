"use client";

import { useState } from "react";
import { ApiError, casesApi, type AIDiagnosisSections, type CaseDetail, type DiagnosisSuggestion, type Summary } from "@/lib/api";
import { Alert, Badge, Button, Card, CardBody, CardHeader, EmptyState, Icons, Input, useToast, type Tone } from "@/components/ui";
import { cn } from "@/lib/utils";
import { AssistantPanel } from "@/features/case/assistant-tab";

const LIKELIHOOD_TONE: Record<DiagnosisSuggestion["likelihood"], Tone> = { high: "danger", medium: "warning", low: "neutral" };

/** What the doctor accepted (or reworded) from the AI differential, with the tests suggested
 * for those - the only part offered to the consultation form. */
export function acceptedDiagnoses(summary: Summary | null | undefined): { conditions: string[]; tests: string[] } {
  const sections = summary?.sections as AIDiagnosisSections | undefined;
  const conditions: string[] = [];
  const tests: string[] = [];
  (sections?.differentials ?? []).forEach((d, i) => {
    const decision = sections?.decisions?.[String(i)];
    if (decision?.decision === "accept" || decision?.decision === "edit") {
      conditions.push(decision.text ?? d.condition);
      tests.push(...d.tests);
    }
  });
  return { conditions, tests: [...new Set(tests)] };
}

/** Decision support in the style of Isabel DDx / Glass Health: a ranked differential drafted at
 * pre-screening, which the doctor accepts, rewords or dismisses item by item. Never shown to the
 * patient; only what the doctor accepts can be copied into the consultation they sign. */
export function DiagnosisTab({ detail, doctorContext, onChanged, onOpenReport }: {
  detail: CaseDetail; doctorContext: string; onChanged: (summary: Summary) => void;
  // Switch to the Review & visit tab, where accepted diagnoses fill the report.
  onOpenReport: () => void;
}) {
  const summary = detail.ai_diagnosis ?? null;
  const sections = summary?.sections as AIDiagnosisSections | undefined;
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ index: number; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const toast = useToast();

  async function run(key: string, call: () => Promise<Summary>) {
    setBusy(key);
    setError(null);
    try {
      onChanged(await call());
      setEditing(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy(null);
    }
  }

  const regenerate = () => run("regenerate", async () => {
    const s = await casesApi.regenerateDiagnosis(detail.case_id);
    toast.push({ tone: "success", message: "AI diagnosis updated" });
    return s;
  });

  const accepted = acceptedDiagnoses(summary);
  const reportOpen = ["NEEDS_REVIEW", "APPROVED", "COMPLETED"].includes(detail.status);
  const released = detail.status === "COMPLETED";
  const reportLabel = released ? "View report" : detail.status === "NEEDS_REVIEW" ? "Review & sign report" : "Open report";

  const action = (
    <div className="flex flex-wrap gap-2">
      <Button size="sm" variant="secondary" loading={busy === "regenerate"} icon={<Icons.refresh size={14} />} onClick={regenerate}>
        {summary ? "Regenerate" : "Generate"}
      </Button>
      {reportOpen ? (
        <Button size="sm" icon={<Icons.arrowRight size={14} />} onClick={onOpenReport}>{reportLabel}</Button>
      ) : null}
    </div>
  );

  return (
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
    <Card>
      <CardHeader
        title="AI diagnosis"
        description="A suggested differential from the intake, records and uploaded reports. Unverified decision support: examine the patient and decide. Never shown to the patient."
        action={action}
      />
      <CardBody className="space-y-5">
        {error ? <Alert tone="danger">{error}</Alert> : null}
        {sections && reportOpen ? (
          <div className="flex flex-col gap-3 rounded-lg border border-brand-ring bg-brand-soft/40 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 text-sm">
              <p className="font-medium">
                {accepted.conditions.length
                  ? `${accepted.conditions.length} accepted ${accepted.conditions.length === 1 ? "diagnosis goes" : "diagnoses go"} into the report`
                  : "Nothing accepted yet"}
              </p>
              <p className="mt-0.5 text-fg-muted">
                {accepted.conditions.length
                  ? `${accepted.conditions.join(", ")}${accepted.tests.length ? `, with ${accepted.tests.length} suggested test${accepted.tests.length === 1 ? "" : "s"}` : ""}. Review and sign it on Review & visit.`
                  : "Accept or edit a diagnosis below and it fills the report's Diagnosis and Investigations sections."}
              </p>
            </div>
            <Button size="sm" variant={accepted.conditions.length ? "primary" : "secondary"} icon={<Icons.arrowRight size={14} />} onClick={onOpenReport} className="shrink-0">
              {reportLabel}
            </Button>
          </div>
        ) : null}
        {!sections ? (
          <EmptyState icon={<Icons.sparkles size={20} />} title="No AI diagnosis yet"
            description="It is drafted when pre-screening finishes. Generate one now if it is missing or the model was unavailable." />
        ) : (
          <>
            {sections.reasoning ? <p className="text-sm leading-6 text-fg-muted">{sections.reasoning}</p> : null}

            {sections.red_flags.length ? (
              <Alert tone="danger" title="Must exclude">
                <ul className="list-disc space-y-0.5 pl-5">{sections.red_flags.map((r) => <li key={r}>{r}</li>)}</ul>
              </Alert>
            ) : null}

            <ol className="space-y-3">
              {sections.differentials.map((d, i) => {
                const decision = sections.decisions?.[String(i)];
                const dismissed = decision?.decision === "dismiss";
                const accepted = decision?.decision === "accept" || decision?.decision === "edit";
                return (
                  <li key={`${d.condition}-${i}`} className={cn(
                    "rounded-lg border p-4",
                    accepted ? "border-success bg-success-soft/40" : "border-line",
                    dismissed && "opacity-60",
                  )}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold text-fg-subtle">{i + 1}.</span>
                      <h3 className={cn("text-[15px] font-semibold", dismissed && "line-through")}>{decision?.text ?? d.condition}</h3>
                      {d.added_by === "doctor"
                        ? <Badge tone="brand">Added by doctor</Badge>
                        : <Badge tone={LIKELIHOOD_TONE[d.likelihood]}>{d.likelihood} likelihood</Badge>}
                      {accepted ? <Badge tone="success" dot>{decision?.decision === "edit" ? "Accepted (edited)" : "Accepted"}</Badge> : null}
                      {dismissed ? <Badge>Dismissed</Badge> : null}
                    </div>
                    {decision?.decision === "edit" ? <p className="mt-1 text-xs text-fg-subtle">AI suggested: {d.condition}</p> : null}

                    <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                      <Points label="Supporting" items={d.supporting} />
                      <Points label="Against" items={d.against} />
                      <Points label="Tests to confirm" items={d.tests} />
                      <Points label="Management if confirmed" items={d.management} />
                    </div>

                    {editing?.index === i ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <label htmlFor={`dx-edit-${i}`} className="sr-only">Diagnosis wording</label>
                        <Input id={`dx-edit-${i}`} value={editing.text} maxLength={300} className="min-w-0 flex-1"
                          onChange={(e) => setEditing({ index: i, text: e.target.value })} />
                        <Button size="sm" loading={busy === `edit-${i}`} disabled={!editing.text.trim()}
                          onClick={() => run(`edit-${i}`, () => casesApi.decideDiagnosis(detail.case_id, i, "edit", editing.text))}>
                          Save
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
                      </div>
                    ) : (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Button size="sm" variant={accepted ? "secondary" : "primary"} icon={<Icons.check size={14} />}
                          loading={busy === `accept-${i}`} disabled={decision?.decision === "accept"}
                          onClick={() => run(`accept-${i}`, () => casesApi.decideDiagnosis(detail.case_id, i, "accept"))}>
                          Accept
                        </Button>
                        <Button size="sm" variant="secondary" icon={<Icons.edit size={14} />}
                          onClick={() => setEditing({ index: i, text: decision?.text ?? d.condition })}>
                          Edit
                        </Button>
                        <Button size="sm" variant="ghost" icon={<Icons.sparkles size={14} />}
                          onClick={() => setQuestion(`Regarding ${decision?.text ?? d.condition}: `)}>
                          Ask about this
                        </Button>
                        <Button size="sm" variant="ghost" icon={<Icons.x size={14} />}
                          loading={busy === `dismiss-${i}`} disabled={dismissed}
                          onClick={() => run(`dismiss-${i}`, () => casesApi.decideDiagnosis(detail.case_id, i, "dismiss"))}>
                          Dismiss
                        </Button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>

            {sections.missing_information.length ? (
              <div>
                <p className="text-xs font-medium text-fg-muted">Would change the differential</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">{sections.missing_information.map((m) => <li key={m}>{m}</li>)}</ul>
              </div>
            ) : null}

            <p className="text-xs text-fg-subtle" suppressHydrationWarning>
              Generated {new Date(summary!.created_at).toLocaleString()}. Accepted diagnoses can be added to the prescription from the Review &amp; visit tab.
            </p>
          </>
        )}
      </CardBody>
    </Card>
    <AssistantPanel caseId={detail.case_id} doctorContext={doctorContext} initialMessages={detail.assistant_messages ?? []}
      text={question} onTextChange={setQuestion}
      onDiagnosisAdded={(s) => { onChanged(s); toast.push({ tone: "success", message: "Added to the diagnosis" }); }} className="lg:sticky lg:top-4" />
    </div>
  );
}

function Points({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <p className="text-xs font-medium text-fg-muted">{label}</p>
      <ul className="mt-0.5 list-disc space-y-0.5 pl-5">{items.map((p) => <li key={p}>{p}</li>)}</ul>
    </div>
  );
}
