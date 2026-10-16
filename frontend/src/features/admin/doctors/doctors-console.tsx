"use client";

import { useState } from "react";
import { adminDoctorsApi, ApiError } from "@/lib/api";
import type { AdminDoctor, AdminDoctors, DoctorRemovalCheck } from "@/lib/api/types";
import { Alert, Badge, Button, Card, CardHeader, Dialog, EmptyState, Field, IconButton, Icons, Select, Skeleton, Table, Td, Th, useToast } from "@/components/ui";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { clockLabel, daysLabel } from "@/features/scheduling/doctor-hours";
import { AddDoctorDialog } from "@/features/admin/doctors/add-doctor-dialog";

const WEEK_OPTIONS = [4, 8, 12, 26];
const RUNNING_LOW_DAYS = 14;

/** "2026-11-11" -> "11 Nov 2026", read as a calendar date (never shifted by the browser's timezone). */
export function dateLabel(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })
    .format(new Date(`${iso}T00:00:00Z`));
}

function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((Date.parse(`${toIso}T00:00:00Z`) - Date.parse(`${fromIso}T00:00:00Z`)) / 86_400_000);
}

function HoursCell({ doctor, today }: { doctor: AdminDoctor; today: string }) {
  if (!doctor.hours.length) return <Badge tone="warning">No hours published</Badge>;
  const left = doctor.hours_until ? daysBetween(today, doctor.hours_until) : 0;
  return (
    <div className="space-y-1 text-xs tabular-nums">
      {doctor.hours.map((group) => (
        <p key={group.days.join("-")}>
          <span className="font-medium text-fg">{daysLabel(group.days)}</span>
          <span className="text-fg-muted"> · {group.times.map(([s, e]) => `${clockLabel(s)} – ${clockLabel(e)}`).join(", ")}</span>
        </p>
      ))}
      {doctor.hours_until ? (
        <p className={left < RUNNING_LOW_DAYS ? "font-medium text-warning" : "text-fg-subtle"}>
          Published until {dateLabel(doctor.hours_until)}
        </p>
      ) : null}
    </div>
  );
}

export function DoctorsConsole({ initial }: { initial: AdminDoctors }) {
  const [doctors, setDoctors] = useState(initial.doctors);
  const [adding, setAdding] = useState(false);
  const [extending, setExtending] = useState<AdminDoctor | null>(null);
  const [weeks, setWeeks] = useState(8);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [removing, setRemoving] = useState<AdminDoctor | null>(null);
  const [removal, setRemoval] = useState<DoctorRemovalCheck | null>(null);
  const [reactivating, setReactivating] = useState<number | null>(null);
  const toast = useToast();
  const { clinic, departments } = initial;
  const departmentName = (id: string | null) => departments.find((d) => d.department_id === id)?.department_name;

  const msg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong.");

  async function refresh() {
    setRefreshing(true);
    try { setDoctors((await adminDoctorsApi.list()).doctors); }
    catch (e) { toast.push({ tone: "danger", message: msg(e) }); }
    finally { setRefreshing(false); }
  }
  async function extend() {
    if (!extending) return;
    setSaving(true);
    try {
      const updated = await adminDoctorsApi.extendHours(extending.id, weeks);
      setDoctors((list) => list.map((d) => (d.id === updated.id ? updated : d)));
      toast.push({ tone: "success", message: `${updated.name}'s hours are now published until ${dateLabel(updated.hours_until ?? "")}.` });
      setExtending(null);
    } catch (e) { toast.push({ tone: "danger", message: msg(e) }); }
    finally { setSaving(false); }
  }

  async function askRemove(doctor: AdminDoctor) {
    setRemoving(doctor); setRemoval(null);
    try { setRemoval(await adminDoctorsApi.removalCheck(doctor.id)); }
    catch (e) { toast.push({ tone: "danger", message: msg(e) }); setRemoving(null); }
  }
  async function remove() {
    if (!removing) return;
    setSaving(true);
    try {
      const { result, doctor } = await adminDoctorsApi.remove(removing.id);
      setDoctors((list) => (doctor ? list.map((d) => (d.id === doctor.id ? doctor : d)) : list.filter((d) => d.id !== removing.id)));
      toast.push({ tone: "success", message: result === "deleted" ? `${removing.name} was deleted.` : `${removing.name} was deactivated. Their records are kept.` });
      setRemoving(null);
    } catch (e) { toast.push({ tone: "danger", message: msg(e) }); }
    finally { setSaving(false); }
  }
  async function reactivate(doctor: AdminDoctor) {
    setReactivating(doctor.id);
    try {
      const updated = await adminDoctorsApi.reactivate(doctor.id);
      setDoctors((list) => list.map((d) => (d.id === updated.id ? updated : d)));
      toast.push({ tone: "success", message: `${updated.name} is active again and can sign in.` });
    } catch (e) { toast.push({ tone: "danger", message: msg(e) }); }
    finally { setReactivating(null); }
  }

  return (
    <div className="pb-12">
      <PageHeader
        title="Doctors"
        description={`Doctors at ${clinic.name}. Adding one creates their hospital-system record, their consulting hours and their CareFlow login in one step.`}
        actions={<>
          <Button variant="secondary" icon={<Icons.refresh size={16} />} loading={refreshing} onClick={refresh}>Refresh</Button>
          <Button icon={<Icons.plus size={16} />} onClick={() => setAdding(true)}>Add doctor</Button>
        </>}
      />

      <Card>
        <CardHeader title={clinic.name} description={`${doctors.length} doctor${doctors.length === 1 ? "" : "s"} · from the hospital system`} />
        {doctors.length === 0 ? (
          <EmptyState icon={<Icons.stethoscope size={20} />} title="No doctors yet"
            description="Add the first doctor so patients can be routed and booked."
            action={<Button icon={<Icons.plus size={16} />} onClick={() => setAdding(true)}>Add doctor</Button>} />
        ) : (
          <Table regionLabel="Doctors">
            <thead>
              <tr><Th>Doctor</Th><Th>Department</Th><Th>NPI</Th><Th>Consulting hours</Th><Th>Login</Th><Th className="w-32"><span className="sr-only">Actions</span></Th></tr>
            </thead>
            <tbody>
              {doctors.map((d) => (
                <tr key={d.id} className={cn(!d.active && "[&_td:not(:last-child)>*]:opacity-60")}>
                  <Td>
                    <p className="font-medium">{d.name}</p>
                    <p className="font-mono text-xs text-fg-subtle">{d.username}</p>
                  </Td>
                  <Td>
                    {d.department_id ? <Badge tone="brand">{departmentName(d.department_id) ?? d.department_id}</Badge> : <Badge tone="warning">Not routed</Badge>}
                    <p className="mt-1 text-xs text-fg-subtle">{d.specialty}</p>
                  </Td>
                  <Td className="font-mono text-xs tabular-nums">{d.npi}</Td>
                  <Td><HoursCell doctor={d} today={clinic.today} /></Td>
                  <Td>
                    {!d.active ? <Badge>Deactivated</Badge>
                      : d.has_login === null ? <Badge>Unknown</Badge>
                      : d.has_login ? <Badge tone="success" dot>Active</Badge>
                      : <Badge tone="warning" dot>No CareFlow login</Badge>}
                  </Td>
                  <Td className="text-right">
                    {d.active ? (
                      <div className="flex items-center justify-end gap-1">
                        <Button size="sm" variant="secondary" icon={<Icons.calendar size={14} />} disabled={!d.can_extend}
                          title={d.can_extend ? undefined : "No published hours to continue"}
                          onClick={() => { setWeeks(8); setExtending(d); }}>Extend hours</Button>
                        <IconButton size="sm" label={`Remove ${d.name}`} icon={<Icons.trash size={14} />} onClick={() => askRemove(d)} />
                      </div>
                    ) : (
                      <Button size="sm" variant="secondary" icon={<Icons.refresh size={14} />} loading={reactivating === d.id}
                        onClick={() => reactivate(d)}>Reactivate</Button>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <AddDoctorDialog open={adding} onClose={() => setAdding(false)} clinic={clinic} departments={departments}
        onCreated={(doctor) => {
          setDoctors((list) => [...list, doctor].sort((a, b) => a.name.localeCompare(b.name)));
          toast.push({ tone: "success", message: `${doctor.name} was added. They can sign in now.` });
          setAdding(false);
        }} />

      <Dialog open={removing !== null} onClose={() => !saving && setRemoving(null)}
        title={removal?.mode === "deactivate" ? "Deactivate doctor" : "Remove doctor"}
        description={removing ? `${removing.name} · ${removing.username}` : undefined}
        footer={<>
          <Button variant="secondary" onClick={() => setRemoving(null)} disabled={saving}>{removal?.blocked_by_open_cases ? "Close" : "Cancel"}</Button>
          {removal && !removal.blocked_by_open_cases ? (
            <Button variant="danger" onClick={remove} loading={saving} icon={<Icons.trash size={16} />}>
              {removal.mode === "delete" ? "Delete doctor" : "Deactivate doctor"}
            </Button>
          ) : null}
        </>}>
        {!removal ? <div className="space-y-2"><Skeleton className="h-5 w-2/3" /><Skeleton className="h-16" /></div> : (
          <div className="space-y-4 text-sm">
            {removal.blocked_by_open_cases ? (
              <Alert tone="danger" title="Can't remove yet">
                {removal.doctor.name} still has {removal.blocked_by_open_cases} open case{removal.blocked_by_open_cases === 1 ? "" : "s"}.
                Finish or reject {removal.blocked_by_open_cases === 1 ? "it" : "them"} first, so no patient is left waiting for a doctor who has gone.
              </Alert>
            ) : removal.mode === "delete" ? (
              <Alert tone="info" title="This doctor has never been used">
                No visits, notes, appointments or CareFlow cases. They will be <span className="font-semibold">permanently deleted</span> from
                the hospital system and their CareFlow login removed.
              </Alert>
            ) : (
              <Alert tone="warning" title="This doctor has patient history, so they will be deactivated">
                Their records stay, with their name on them. They stop receiving patients and can no longer sign in or sign off.
                You can reactivate them later.
              </Alert>
            )}
            {removal.mode === "deactivate" ? (
              <ul className="grid grid-cols-2 gap-x-6 gap-y-1 text-fg-muted sm:grid-cols-3">
                <li><span className="tabular-nums font-medium text-fg">{removal.history.cases}</span> CareFlow cases</li>
                <li><span className="tabular-nums font-medium text-fg">{removal.history.notes}</span> consultation notes</li>
                <li><span className="tabular-nums font-medium text-fg">{removal.history.encounters}</span> visits</li>
                <li><span className="tabular-nums font-medium text-fg">{removal.history.forms}</span> chart forms</li>
                <li><span className="tabular-nums font-medium text-fg">{removal.history.appointments}</span> appointments</li>
              </ul>
            ) : null}
            {removal.last_in_department && !removal.blocked_by_open_cases ? (
              <Alert tone="warning" title="Last doctor in this department">
                New patients for this department will go to the default department until another doctor is added.
              </Alert>
            ) : null}
          </div>
        )}
      </Dialog>

      <Dialog open={extending !== null} onClose={() => setExtending(null)} title="Extend consulting hours"
        description={extending ? `Publish ${extending.name}'s current weekly hours for more weeks.` : undefined}
        footer={<>
          <Button variant="secondary" onClick={() => setExtending(null)} disabled={saving}>Cancel</Button>
          <Button onClick={extend} loading={saving} icon={<Icons.check size={16} />}>Extend hours</Button>
        </>}>
        {extending ? (
          <div className="space-y-4">
            <p className="text-sm text-fg-muted">
              Currently published until <span className="font-medium text-fg">{extending.hours_until ? dateLabel(extending.hours_until) : "–"}</span>.
              The last published week is repeated, day by day.
            </p>
            <Field label="Add" htmlFor="extend-weeks">
              <Select id="extend-weeks" value={weeks} onChange={(e) => setWeeks(Number(e.target.value))}>
                {WEEK_OPTIONS.map((w) => <option key={w} value={w}>{w} weeks</option>)}
              </Select>
            </Field>
          </div>
        ) : null}
      </Dialog>
    </div>
  );
}
