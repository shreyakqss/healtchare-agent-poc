"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { HMSStatus, HospitalSummary } from "@/lib/api/types";
import { Badge, Button, Card, CardBody, CardHeader, Dialog, Field, Icons, Input, KeyValue, SectionTitle } from "@/components/ui";
import { HOSPITAL_ID_PATTERN } from "@/features/admin/validate";

export function HospitalsRail({ hospitals, selectedId, busy, hms, onSelect, onActivate, onCreate, onDelete }: {
  hospitals: HospitalSummary[]; selectedId: string | null; busy: boolean; hms: HMSStatus | null;
  onSelect: (id: string) => void; onActivate: (id: string) => void; onCreate: (id: string) => Promise<void>; onDelete: (id: string) => Promise<void>;
}) {
  const [createOpen, setCreateOpen] = useState(false);
  const [newId, setNewId] = useState("");
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const idValid = HOSPITAL_ID_PATTERN.test(newId);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title="Clinics" description="One configuration file per clinic. Exactly one is active."
          action={<Button size="sm" variant="secondary" icon={<Icons.plus size={14} />} onClick={() => setCreateOpen(true)}>New</Button>} />
        <ul className="divide-y divide-line">
          {hospitals.map((h) => {
            const selected = h.id === selectedId;
            return (
              <li key={h.id}>
                <button type="button" onClick={() => onSelect(h.id)} aria-current={selected ? "true" : undefined}
                  className={cn("flex w-full items-start justify-between gap-3 px-5 py-3 text-left transition-colors hover:bg-sunken", selected && "bg-brand-soft/60")}>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{h.name}</p>
                    <p className="truncate font-mono text-xs text-fg-subtle">{h.id}</p>
                    <p className="tabular mt-1 text-xs text-fg-muted">{h.departments} depts · {h.doctors} doctors · {h.rules} rules</p>
                  </div>
                  {h.active ? <Badge tone="success" dot>Active</Badge> : null}
                </button>
                {selected ? (
                  <div className="flex gap-2 px-5 pb-3">
                    {!h.active ? <Button size="sm" onClick={() => onActivate(h.id)} disabled={busy}>Activate</Button> : null}
                    <Button size="sm" variant="ghost" icon={<Icons.trash size={14} />} disabled={h.active || busy} onClick={() => setDeleteId(h.id)}
                      title={h.active ? "The active clinic cannot be deleted" : undefined}>Delete</Button>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      </Card>

      <Card>
        <CardBody>
          <SectionTitle>Hospital management system</SectionTitle>
          {hms ? (
            <KeyValue className="mt-3" items={[
              { label: "Provider", value: <span className="capitalize">{hms.provider}</span> },
              { label: "Connection", value: <Badge tone={hms.connected ? "success" : "danger"} dot>{hms.connected ? "Connected" : "Offline"}</Badge> },
              { label: "Patients on record", value: <span className="tabular">{hms.patients}</span> },
              { label: "Practitioners", value: <span className="tabular">{hms.practitioners}</span> },
              { label: "Pending appointment requests", value: <span className="tabular">{hms.pending_requests}</span> },
            ]} />
          ) : <p className="mt-2 text-sm text-fg-muted">Status unavailable.</p>}
          <p className="mt-3 text-xs text-fg-subtle">Read-only. The adapter is configured on the server (HMS_PROVIDER).</p>
        </CardBody>
      </Card>

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} title="New clinic" description="Starts as a copy of the active clinic, so it is valid on arrival."
        footer={<>
          <Button variant="secondary" onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button disabled={!idValid || busy} loading={busy} onClick={async () => { await onCreate(newId); setCreateOpen(false); setNewId(""); }}>Create</Button>
        </>}>
        <Field label="Clinic id" htmlFor="new-clinic-id" required hint="Lowercase letters, digits and hyphens. This becomes the file name and cannot be changed."
          error={newId && !idValid ? "Use 2–63 characters: a-z, 0-9, hyphens; must start with a letter or digit." : null}>
          <Input id="new-clinic-id" value={newId} onChange={(e) => setNewId(e.target.value.trim())} placeholder="northside-family-clinic" autoComplete="off" />
        </Field>
      </Dialog>

      <Dialog open={deleteId !== null} onClose={() => setDeleteId(null)} title="Delete clinic?" description="The configuration file is removed. Cases already triaged keep their rule references."
        footer={<>
          <Button variant="secondary" onClick={() => setDeleteId(null)}>Cancel</Button>
          <Button variant="danger" loading={busy} onClick={async () => { if (deleteId) await onDelete(deleteId); setDeleteId(null); }}>Delete</Button>
        </>}>
        <p className="text-sm">This will delete <span className="font-mono">{deleteId}</span>. This cannot be undone.</p>
      </Dialog>
    </div>
  );
}