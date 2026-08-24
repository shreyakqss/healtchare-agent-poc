"use client";

import type { AppointmentType, HospitalConfig, Priority } from "@/lib/api/types";
import { PRIORITY_LABEL } from "@/lib/constants";
import { Button, Card, CardBody, CardHeader, EmptyState, Field, Icons, IconButton, Input, PriorityBadge, Select, Table, Td, Th } from "@/components/ui";
import { slugify, type ConfigEditor } from "@/features/admin/use-config-editor";

const PRIORITIES: Priority[] = ["high", "medium", "low"];

export function AppointmentsTab({ editor }: { editor: ConfigEditor }) {
  const cfg = editor.config as HospitalConfig;
  const types = cfg.appointment_types ?? [];
  const map = cfg.priority_appointment_map ?? ({} as HospitalConfig["priority_appointment_map"]);
  const setTypes = (next: AppointmentType[]) => editor.update((c) => ({ ...c, appointment_types: next }));
  const edit = (i: number, patch: Partial<AppointmentType>) => setTypes(types.map((t, j) => (j === i ? { ...t, ...patch } : t)));

  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <Card className="lg:col-span-3">
        <CardHeader title="Appointment types" description="The kinds of visit the clinic offers."
          action={<Button size="sm" variant="secondary" icon={<Icons.plus size={14} />} onClick={() => setTypes([...types, { id: `type_${types.length + 1}`, label: "", duration_minutes: 20 }])}>Add type</Button>} />
        {types.length === 0 ? <EmptyState title="No appointment types" /> : (
          <Table>
            <thead><tr><Th>Id</Th><Th>Label</Th><Th className="w-28">Minutes</Th><Th className="w-16"><span className="sr-only">Actions</span></Th></tr></thead>
            <tbody>
              {types.map((t, i) => (
                <tr key={i}>
                  <Td><Input aria-label="Type id" value={t.id} className="h-9 font-mono text-xs" onChange={(e) => edit(i, { id: slugify(e.target.value) })} /></Td>
                  <Td><Input aria-label="Label" value={t.label} className="h-9" onChange={(e) => edit(i, { label: e.target.value })} /></Td>
                  <Td><Input aria-label="Duration in minutes" type="number" min={5} step={5} value={t.duration_minutes ?? ""} className="h-9 tabular" onChange={(e) => edit(i, { duration_minutes: Number(e.target.value) || undefined })} /></Td>
                  <Td><IconButton size="sm" label="Remove type" icon={<Icons.trash size={14} />} onClick={() => setTypes(types.filter((_, j) => j !== i))} /></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      <Card className="lg:col-span-2">
        <CardHeader title="Priority to appointment" description="Which appointment type each administrative priority proposes." />
        <CardBody className="space-y-4">
          {PRIORITIES.map((p) => (
            <Field key={p} label={`${PRIORITY_LABEL[p]} priority`} htmlFor={`map-${p}`}>
              <div className="flex items-center gap-3">
                <PriorityBadge priority={p} />
                <Select id={`map-${p}`} value={map[p] ?? ""} onChange={(e) => editor.update((c) => ({ ...c, priority_appointment_map: { ...c.priority_appointment_map, [p]: e.target.value } }))}>
                  <option value="">Choose one</option>
                  {types.map((t) => <option key={t.id} value={t.id}>{t.label || t.id}</option>)}
                </Select>
              </div>
            </Field>
          ))}
        </CardBody>
      </Card>
    </div>
  );
}