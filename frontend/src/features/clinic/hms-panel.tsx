import { Alert, Badge, BarList, Card, CardBody, CardHeader, EmptyState, Icons, KeyValue, Table, Td, Th } from "@/components/ui";
import type { AppointmentRequestResult, ClinicOverview, HMSStatus, HospitalConfig } from "@/lib/api/types";
import { PRIORITY_LABEL } from "@/lib/constants";
import { formatDateTime } from "@/lib/utils";
import type { Priority } from "@/lib/api/types";

const PRIORITY_TONE_BAR: Record<Priority, string> = { high: "bg-danger", medium: "bg-warning", low: "bg-success" };

export function HmsPanel({ status, requests, overview, config }: {
  status: HMSStatus | null; requests: AppointmentRequestResult[]; overview: ClinicOverview | null; config: HospitalConfig | null;
}) {
  const doctors = new Map((config?.doctors ?? []).map((d) => [d.id, d.name]));
  return (
    <div className="space-y-4">
      <Alert tone="info" title="Appointment requests are drafts">
        After a clinician approves a case, the finalisation step sends an appointment <em>request</em> to the hospital management system. Nothing is booked. HMS staff confirm the slot.
      </Alert>
      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader title="Connection" action={status ? <Badge tone={status.connected ? "success" : "danger"} dot>{status.connected ? "Connected" : "Offline"}</Badge> : <Badge>Unknown</Badge>} />
            <CardBody>
              {status ? (
                <KeyValue items={[
                  { label: "Provider", value: <span className="font-mono">{status.provider}</span> },
                  { label: "Patients in registry", value: status.patients },
                  { label: "Practitioners", value: status.practitioners },
                  { label: "Pending requests", value: status.pending_requests },
                ]} columns={2} />
              ) : <p className="text-sm text-fg-muted">Status unavailable.</p>}
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Priority breakdown" />
            <CardBody>
              <BarList items={(["high", "medium", "low"] as Priority[]).map((p) => ({ label: PRIORITY_LABEL[p], value: overview?.by_priority?.[p] ?? 0, tone: PRIORITY_TONE_BAR[p] }))} />
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Departments by volume" />
            <CardBody>
              {overview && Object.keys(overview.by_department).length ? (
                <BarList items={Object.entries(overview.by_department).sort((a, b) => b[1] - a[1]).map(([label, value]) => ({ label, value }))} />
              ) : <p className="text-sm text-fg-muted">No routed cases yet.</p>}
            </CardBody>
          </Card>
        </div>
        <Card>
          <CardHeader title="Appointment requests" description="Sent to the HMS after clinician approval" />
          {requests.length === 0 ? (
            <EmptyState icon={<Icons.calendar size={20} />} title="No requests yet" description="Requests appear once a case is finalised." />
          ) : (
            <Table>
              <thead><tr><Th>Reference</Th><Th>Status</Th><Th>Practitioner</Th><Th>Proposed slot</Th></tr></thead>
              <tbody>
                {requests.map((r) => (
                  <tr key={r.reference}>
                    <Td className="font-mono text-xs">{r.reference}</Td>
                    <Td><Badge tone="warning">{r.status}</Badge></Td>
                    <Td>{r.slot ? (doctors.get(r.slot.practitioner_id) ?? r.slot.practitioner_id) : "–"}</Td>
                    <Td className="text-fg-muted" suppressHydrationWarning>{r.slot ? formatDateTime(r.slot.start) : "No slot available"}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>
    </div>
  );
}