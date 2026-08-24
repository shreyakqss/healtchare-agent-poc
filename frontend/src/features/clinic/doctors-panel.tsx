import Link from "next/link";
import { Avatar, BarList, Button, Card, CardBody, CardHeader, EmptyState, Icons, Table, Td, Th } from "@/components/ui";
import type { CaseListItem, HospitalConfig } from "@/lib/api/types";
import { doctorLoads } from "@/features/clinic/derive";

export function DoctorsPanel({ cases, config }: { cases: CaseListItem[]; config: HospitalConfig | null }) {
  if (!config) return <EmptyState icon={<Icons.stethoscope size={20} />} title="Clinic configuration unavailable" description="The roster comes from the active hospital configuration." />;
  const depts = new Map(config.departments.map((d) => [d.id, d.name]));
  const loads = doctorLoads(config.doctors, cases);
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <Card>
        <CardHeader title="Roster" description="Open cases are non-terminal cases assigned to the doctor." action={<Link href="/doctor"><Button variant="secondary" size="sm" iconRight={<Icons.arrowRight size={14} />}>Doctor workspace</Button></Link>} />
        <Table>
          <thead>
            <tr><Th>Doctor</Th><Th>Department</Th><Th>Working days</Th><Th className="text-right">Open</Th><Th className="text-right">Awaiting review</Th><Th className="text-right">Completed</Th></tr>
          </thead>
          <tbody>
            {loads.map(({ doctor, open, awaiting, completed }) => (
              <tr key={doctor.id}>
                <Td><span className="flex items-center gap-2.5"><Avatar name={doctor.name} size="sm" /><span className="font-medium">{doctor.name}</span></span></Td>
                <Td className="text-fg-muted">{depts.get(doctor.department_id) ?? doctor.department_id}</Td>
                <Td className="text-fg-muted">{(doctor.working_days ?? []).map((d) => d[0].toUpperCase() + d.slice(1)).join(", ") || "–"}</Td>
                <Td className="tabular text-right">{open}</Td>
                <Td className="tabular text-right">{awaiting ? <span className="font-medium text-warning">{awaiting}</span> : 0}</Td>
                <Td className="tabular text-right text-fg-muted">{completed}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
      <Card>
        <CardHeader title="Load" description="Open cases per doctor" />
        <CardBody>
          <BarList items={loads.map((l) => ({ label: l.doctor.name, value: l.open }))} />
        </CardBody>
      </Card>
    </div>
  );
}