"use client";

import type { HospitalConfig } from "@/lib/api/types";
import { Card, CardBody, CardHeader, Field, Input, KeyValue } from "@/components/ui";
import type { ConfigEditor } from "@/features/admin/use-config-editor";

export function GeneralTab({ editor, hospitalId }: { editor: ConfigEditor; hospitalId: string }) {
  const cfg = editor.config as HospitalConfig;
  const set = (patch: Partial<HospitalConfig["hospital"]>) => editor.update((c) => ({ ...c, hospital: { ...c.hospital, ...patch } }));
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader title="Clinic details" description="Shown in the patient portal header and on every case." />
        <CardBody className="grid gap-4 sm:grid-cols-2">
          <Field label="Display name" htmlFor="h-name" required>
            <Input id="h-name" value={cfg.hospital?.name ?? ""} onChange={(e) => set({ name: e.target.value })} />
          </Field>
          <Field label="Timezone" htmlFor="h-tz" hint="IANA name, e.g. Asia/Kolkata">
            <Input id="h-tz" value={cfg.hospital?.timezone ?? ""} onChange={(e) => set({ timezone: e.target.value })} />
          </Field>
          <Field label="Identifier" htmlFor="h-id" hint="Fixed at creation; it is the configuration file name.">
            <Input id="h-id" value={hospitalId} readOnly aria-readonly className="bg-sunken font-mono" />
          </Field>
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="At a glance" />
        <CardBody>
          <KeyValue columns={2} items={[
            { label: "Departments", value: <span className="tabular">{cfg.departments?.length ?? 0}</span> },
            { label: "Doctors", value: <span className="tabular">{cfg.doctors?.length ?? 0}</span> },
            { label: "Appointment types", value: <span className="tabular">{cfg.appointment_types?.length ?? 0}</span> },
            { label: "Triage rules", value: <span className="tabular">{cfg.triage_rules?.rules?.length ?? 0}</span> },
            { label: "Rule version", value: <span className="font-mono text-xs">{cfg.triage_rules?.version ?? "–"}</span> },
            { label: "Intake fields", value: <span className="tabular">{cfg.required_intake_fields?.length ?? 0}</span> },
          ]} />
        </CardBody>
      </Card>
    </div>
  );
}