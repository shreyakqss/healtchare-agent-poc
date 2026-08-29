"use client";

import type { CaseDetail } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { Alert, Badge, Card, CardBody, CardHeader, EmptyState, Icons, KeyValue, PriorityBadge, SectionTitle, Table, Td, Th } from "@/components/ui";

export function TriageEvidence({ c }: { c: CaseDetail }) {
  const t = c.triage;
  if (!t) {
    return (
      <Card>
        <CardHeader title="Administrative priority" />
        <EmptyState icon={<Icons.flag size={18} />} title="Not triaged yet" />
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader
        title="Administrative priority"
        description="Set by the clinic's approved rules, not by the AI. Every priority traces to a rule and the statement that matched it."
        action={<PriorityBadge priority={t.priority} />}
      />
      <CardBody className="space-y-5">
        {t.warnings.map((w, i) => (
          <Alert key={i} tone="danger" title="Allergy / medication overlap">{w.message}</Alert>
        ))}
        <div className="space-y-3">
          {t.rules.map((r) => (
            <div key={r.code} className="rounded-md border border-line bg-sunken/60 px-3.5 py-3">
              <div className="flex items-center gap-2">
                <code className="font-mono text-xs font-semibold text-fg">{r.code}</code>
                <Badge>v{r.version}</Badge>
              </div>
              <p className="mt-1.5 text-sm">{r.explanation}</p>
              <p className="mt-1 text-[13px] text-fg-muted"><span className="font-medium text-fg">Action:</span> {r.action}</p>
            </div>
          ))}
          {!t.rules.length && t.rule_codes.length ? <p className="text-sm text-fg-muted">Rule {t.rule_codes.join(", ")} (retired from the current configuration).</p> : null}
        </div>
        <div>
          <SectionTitle>Evidence</SectionTitle>
          <div className="mt-2 overflow-hidden rounded-md border border-line">
            <Table regionLabel="Triage evidence">
              <thead><tr><Th>Matched on</Th><Th>Keyword</Th><Th>Patient statement</Th></tr></thead>
              <tbody>
                {t.evidence.map((e, i) => (
                  <tr key={i}>
                    <Td className="whitespace-nowrap text-fg-muted">{e.matched_on.replace(/_/g, " ")}{e.days !== undefined ? ` (${e.days} d ≥ ${e.threshold_days} d)` : ""}</Td>
                    <Td className="whitespace-nowrap">{e.keyword ? <Badge tone="brand">{e.keyword}</Badge> : "–"}</Td>
                    <Td>{e.text}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        </div>
        <p className="text-xs text-fg-subtle">Evaluated {formatDateTime(t.created_at)}.</p>
      </CardBody>
    </Card>
  );
}

export function RoutingCard({ c }: { c: CaseDetail }) {
  const r = c.routing;
  if (!r) return null;
  return (
    <Card>
      <CardHeader title="Proposed routing" description="Advisory. You may accept or change it during review." />
      <CardBody className="space-y-4">
        <KeyValue
          columns={2}
          items={[
            { label: "Department", value: r.department_name },
            { label: "Appointment type", value: r.appointment_type_label },
            { label: "Doctor", value: r.doctor_name ?? "Unassigned" },
            { label: "Earliest HMS slot", value: r.suggested_slot ? formatDateTime(r.suggested_slot.start) : "None found" },
          ]}
        />
        <p className="text-sm leading-6 text-fg-muted">{r.rationale}</p>
        {r.matched_keywords.length ? (
          <div className="flex flex-wrap gap-1.5">{r.matched_keywords.map((k) => <Badge key={k}>{k}</Badge>)}</div>
        ) : null}
      </CardBody>
    </Card>
  );
}
