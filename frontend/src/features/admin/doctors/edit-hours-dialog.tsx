"use client";

import { useState } from "react";
import { adminDoctorsApi, ApiError } from "@/lib/api";
import type { AdminDoctor, HoursChangePreview } from "@/lib/api/types";
import { Alert, Button, Dialog, Icons } from "@/components/ui";
import { DoctorHours } from "@/features/scheduling/doctor-hours";
import { HoursFields, hoursIssue, sortedRanges, type HoursDraft } from "@/features/admin/doctors/hours-fields";

const WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

/** The doctor's current pattern as a starting point. The form sets one set of ranges for every
 * chosen day, so a doctor whose days differ starts from their first group's times. */
function draftFrom(doctor: AdminDoctor, today: string): HoursDraft {
  const days = WEEK.filter((d) => doctor.hours.some((g) => g.days.includes(d)));
  const ranges = doctor.hours[0]?.times.map(([s, e]) => [s, e] as [string, string]) ?? [["10:00", "13:00"]];
  return { days: days.length ? days : ["mon", "tue", "wed", "thu", "fri"], ranges, start_date: today, weeks: 8 };
}

/** Clinic-local ISO time -> "Mon 19 Oct, 10:30", as wall-clock text (never the browser's timezone). */
function heldLabel(iso: string): string {
  const [day, clock] = iso.split("T");
  const date = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })
    .format(new Date(`${day}T00:00:00Z`));
  return `${date}, ${clock.slice(0, 5)}`;
}

export function EditHoursDialog({ doctor, today, onClose, onSaved }: {
  doctor: AdminDoctor; today: string; onClose: () => void; onSaved: (doctor: AdminDoctor) => void;
}) {
  const [draft, setDraft] = useState<HoursDraft>(() => draftFrom(doctor, today));
  const [touched, setTouched] = useState(false);
  const [preview, setPreview] = useState<HoursChangePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mixed = doctor.hours.length > 1;
  const issue = hoursIssue(draft);
  const body = () => ({ ...draft, ranges: sortedRanges(draft.ranges) });

  function close() { if (!busy) onClose(); }
  async function review() {
    setTouched(true);
    if (issue) return;
    setBusy(true); setError(null);
    try { setPreview(await adminDoctorsApi.previewHours(doctor.id, body())); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not check the new hours."); }
    finally { setBusy(false); }
  }
  async function save() {
    setBusy(true); setError(null);
    try { onSaved(await adminDoctorsApi.changeHours(doctor.id, body())); }
    catch (e) { setError(e instanceof ApiError ? e.message : "The hours could not be changed. Nothing was saved."); }
    finally { setBusy(false); }
  }

  const footer = preview ? (
    <>
      <Button variant="secondary" onClick={() => { setPreview(null); setError(null); }} disabled={busy} icon={<Icons.arrowLeft size={16} />}>Back</Button>
      <Button onClick={save} loading={busy} disabled={!!preview.problems.length} icon={<Icons.check size={16} />}>Save hours</Button>
    </>
  ) : (
    <>
      <Button variant="secondary" onClick={close} disabled={busy}>Cancel</Button>
      <Button onClick={review} loading={busy} iconRight={<Icons.arrowRight size={16} />}>Review</Button>
    </>
  );

  return (
    <Dialog open onClose={close} size="lg" title="Edit consulting hours"
      description={`${doctor.name}. From the date you pick, these hours replace what is published; earlier days stay as they are.`}
      footer={footer}>
      {error ? <Alert tone="danger" title="Not saved" className="mb-4">{error}</Alert> : null}
      {!preview ? (
        <div className="space-y-4">
          {mixed ? (
            <Alert tone="info" title="Hours currently differ by day">
              This form sets one set of times for every day you pick. It starts from their {doctor.hours[0].days.length > 1 ? "first group of days" : "first day"}.
            </Alert>
          ) : null}
          <HoursFields value={draft} onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))} today={today}
            error={touched ? issue : null} idPrefix="eh" startLabel="New hours from" />
        </div>
      ) : (
        <div className="space-y-5">
          {preview.problems.length ? (
            <Alert tone="warning" title="Fix these before saving">
              <ul className="list-disc pl-4">{preview.problems.map((p) => <li key={p}>{p}</li>)}</ul>
            </Alert>
          ) : preview.held_outside.length ? (
            <Alert tone="warning" title={`${preview.held_outside.length} patient time${preview.held_outside.length === 1 ? "" : "s"} fall outside the new hours`}>
              <p>These patients keep their time; nobody is moved or told automatically. Contact them, or check the times are still workable.</p>
              <ul className="mt-1.5 list-disc pl-4 tabular-nums">{preview.held_outside.map((t) => <li key={t}>{heldLabel(t)}</li>)}</ul>
            </Alert>
          ) : (
            <Alert tone="success" title="Ready to save">No patient&apos;s held time falls outside the new hours.</Alert>
          )}
          <div>
            <p className="mb-1.5 text-sm font-medium">What patients will see</p>
            {preview.hours.length ? <DoctorHours hours={preview.hours} /> : <p className="text-xs text-fg-subtle">No hours fall in the first two weeks.</p>}
          </div>
          {preview.hours_until ? (
            <p className="text-sm text-fg-muted">Published from <span className="font-medium text-fg">{draft.start_date}</span> until <span className="font-medium text-fg">{preview.hours_until}</span>.</p>
          ) : null}
        </div>
      )}
    </Dialog>
  );
}
