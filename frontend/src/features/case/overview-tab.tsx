import type { CaseDetail } from "@/lib/api";
import { Card, CardBody, CardHeader, SectionTitle } from "@/components/ui/card";
import { Badge, PriorityBadge } from "@/components/ui/badge";
import { Alert, EmptyState } from "@/components/ui/feedback";
import { KeyValue, Table, Td, Th } from "@/components/ui/data";
import { Icons } from "@/components/ui/icons";
import { FIELD_LABEL } from "@/lib/constants";
import { formatDateTime, titleCase } from "@/lib/utils";

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v : null;
}
function list(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}

function Bullets({ items, empty = "None recorded" }: { items: string[]; empty?: string }) {
  if (!items.length) return <p className="text-sm text-fg-subtle">{empty}</p>;
  return (
    <ul className="space-y-1 text-sm">
      {items.map((x, i) => (
        <li key={i} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-fg-subtle" aria-hidden="true" />{x}</li>
      ))}
    </ul>
  );
}

export function OverviewTab({ detail }: { detail: CaseDetail }) {
  const s = detail.prescreening_summary;
  const sec = (s?.sections ?? {}) as Record<string, unknown>;
  const t = detail.triage;
  const r = detail.routing;
  const rules = t
    ? (t.rules.length ? t.rules : t.rule_codes.map((code) => ({ code, priority: t.priority, explanation: "", action: "", version: "" })))
    : [];

  return (
    <div className="grid gap-5 lg:grid-cols-5">
      <div className="space-y-5 lg:col-span-3">
        <Card>
          <CardHeader
            title="Clinician briefing"
            description="What the patient reported, summarised for the consultation."
            action={s ? <Badge tone={s.generated_by === "llm" ? "brand" : "neutral"}>{s.generated_by === "llm" ? "AI draft" : "Plain listing"}</Badge> : null}
          />
          <CardBody>
            {!s ? (
              <EmptyState icon={<Icons.file size={20} />} title="No briefing yet" description="Pre-screening has not run for this visit." />
            ) : (
              <div className="space-y-5">
                <div>
                  <SectionTitle>Chief complaint</SectionTitle>
                  <p className="mt-1 text-[15px] font-medium">{str(sec.chief_complaint) ?? "Not recorded"}</p>
                </div>
                <div className="grid gap-5 sm:grid-cols-2">
                  <div><SectionTitle>Reported symptoms</SectionTitle><div className="mt-1.5"><Bullets items={list(sec.reported_symptoms)} /></div></div>
                  <div><SectionTitle>Relevant history</SectionTitle><div className="mt-1.5"><Bullets items={list(sec.relevant_history)} /></div></div>
                  <div><SectionTitle>Medications</SectionTitle><div className="mt-1.5"><Bullets items={list(sec.medications)} /></div></div>
                  <div><SectionTitle>Allergies</SectionTitle><div className="mt-1.5"><Bullets items={list(sec.allergies)} /></div></div>
                </div>
                {str(sec.context_for_clinician) ? (
                  <div>
                    <SectionTitle>Context for the clinician</SectionTitle>
                    <p className="mt-1.5 text-sm leading-6 text-fg">{str(sec.context_for_clinician)}</p>
                  </div>
                ) : null}
                {s.missing_information.length ? (
                  <Alert tone="warning" title="Missing information">
                    <ul className="mt-1 list-disc space-y-0.5 pl-4">{s.missing_information.map((m) => <li key={m}>{m}</li>)}</ul>
                  </Alert>
                ) : null}
                {detail.missing_fields.length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {detail.missing_fields.map((f) => <Badge key={f} tone="warning">Not collected: {FIELD_LABEL[f] ?? titleCase(f)}</Badge>)}
                  </div>
                ) : null}
                <p className="text-xs text-fg-subtle" suppressHydrationWarning>Generated {formatDateTime(s.created_at)}</p>
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardBody>
            <KeyValue columns={3} items={[
              { label: "Consent", value: titleCase(detail.consent_status.toLowerCase()) },
              { label: "Clinic", value: detail.hospital_id },
              { label: "Session", value: <span className="font-mono text-xs">{detail.session_id.slice(0, 8)}</span> },
            ]} />
          </CardBody>
        </Card>
      </div>

      <div className="space-y-5 lg:col-span-2">
        <Card>
          <CardHeader title="Administrative priority" action={<PriorityBadge priority={t?.priority ?? null} />} />
          <CardBody className="space-y-4">
            {!t ? (
              <p className="text-sm text-fg-subtle">Not evaluated yet.</p>
            ) : (
              <>
                {t.warnings.length ? (
                  <Alert tone="danger" title="Needs clinician attention">
                    <ul className="space-y-0.5">{t.warnings.map((w, i) => <li key={i}>{w.message}</li>)}</ul>
                  </Alert>
                ) : null}
                <div className="space-y-3">
                  {rules.map((rule) => (
                    <div key={rule.code} className="rounded-md border border-line bg-sunken p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-xs font-semibold">{rule.code}</span>
                        {rule.version ? <span className="text-[11px] text-fg-subtle">v{rule.version}</span> : null}
                      </div>
                      {rule.explanation ? <p className="mt-1.5 text-sm">{rule.explanation}</p> : null}
                      {rule.action ? <p className="mt-1 text-xs text-fg-muted"><span className="font-medium">Action:</span> {rule.action}</p> : null}
                    </div>
                  ))}
                </div>
                {t.evidence.length ? (
                  <div>
                    <SectionTitle className="mb-2">Evidence</SectionTitle>
                    <Table regionLabel="Triage evidence">
                      <thead><tr><Th>Matched on</Th><Th>Detail</Th></tr></thead>
                      <tbody>
                        {t.evidence.map((e, i) => (
                          <tr key={i}>
                            <Td className="whitespace-nowrap text-xs text-fg-muted">
                              {titleCase(e.matched_on)}
                              {e.keyword ? <span className="ml-1 font-mono text-fg">&ldquo;{e.keyword}&rdquo;</span> : null}
                            </Td>
                            <Td className="text-sm">
                              {e.text}
                              {e.days !== undefined ? <span className="ml-1 text-xs text-fg-subtle">({e.days} d &ge; {e.threshold_days} d)</span> : null}
                            </Td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                ) : null}
                <p className="flex items-start gap-1.5 text-xs text-fg-subtle"><Icons.shield size={14} className="mt-0.5 shrink-0" /> Set by the clinic&rsquo;s approved rules. No AI model decides a priority.</p>
              </>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Proposed routing" description="Advisory. Staff may override it." />
          <CardBody>
            {!r ? (
              <p className="text-sm text-fg-subtle">Not routed yet.</p>
            ) : (
              <div className="space-y-4">
                <KeyValue columns={2} items={[
                  { label: "Department", value: r.department_name },
                  { label: "Appointment type", value: r.appointment_type_label },
                  { label: "Doctor", value: r.doctor_name ?? <span className="text-fg-subtle">None rostered</span> },
                  { label: "Proposed slot", value: r.suggested_slot ? <span suppressHydrationWarning>{formatDateTime(r.suggested_slot.start)}</span> : <span className="text-fg-subtle">No open slot</span> },
                ]} />
                <p className="text-sm leading-6 text-fg-muted">{r.rationale}</p>
                {r.matched_keywords.length ? (
                  <div className="flex flex-wrap gap-1.5">{r.matched_keywords.map((k) => <Badge key={k}>{k}</Badge>)}</div>
                ) : null}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
