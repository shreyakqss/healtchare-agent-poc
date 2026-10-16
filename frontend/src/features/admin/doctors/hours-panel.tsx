"use client";

import { useState } from "react";
import { adminDoctorsApi, ApiError } from "@/lib/api";
import type { AdminDoctor, HoursChangePreview } from "@/lib/api/types";
import { Alert, Button, Field, Icons, Select } from "@/components/ui";
import { DoctorHours } from "@/features/scheduling/doctor-hours";
import { HoursFields, type HoursDraft } from "@/features/admin/doctors/hours-fields";

const WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const WEEK_OPTIONS = [4, 8, 12, 26];

/** The doctor's current pattern as a starting point. The form sets one set of ranges for every
 * chosen day, so a doctor whose days differ starts from their first group's times. */
export function hoursDraftFrom(doctor: AdminDoctor, today: string): HoursDraft {
  const days = WEEK.filter((d) => doctor.hours.some((g) => g.days.includes(d)));
  const ranges = doctor.hours[0]?.times.map(([s, e]) => [s, e] as [string, string]) ?? [["10:00", "13:00"]];
  return { days: days.length ? days : ["mon", "tue", "wed", "thu", "fri"], ranges, start_date: today, weeks: 8 };
}

/** "2026-11-11" -> "11 Nov 2026", read as a calendar date (never shifted by the browser's timezone). */
export function dateLabel(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })
    .format(new Date(`${iso}T00:00:00Z`));
}

/** Clinic-local ISO time -> "Mon 19 Oct, 10:30", as wall-clock text (never the browser's timezone). */
function heldLabel(iso: string): string {
  const [day, clock] = iso.split("T");
  const date = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })
    .format(new Date(`${day}T00:00:00Z`));
  return `${date}, ${clock.slice(0, 5)}`;
}

/** Edit doctor > Hours. The new pattern is part of the dialog's one Save; extending is its own
 * one-click action, allowed only while nothing else in the dialog is unsaved. */
export function HoursPanel({ doctor, today, draft, onChange, error, hasUnsaved, onExtended }: {
  doctor: AdminDoctor; today: string; draft: HoursDraft; onChange: (patch: Partial<HoursDraft>) => void;
  error: string | null; hasUnsaved: boolean; onExtended: (doctor: AdminDoctor, message: string) => void;
}) {
  const [extendWeeks, setExtendWeeks] = useState(8);
  const [extending, setExtending] = useState(false);
  const [extendError, setExtendError] = useState<string | null>(null);
  const blocked = !doctor.can_extend ? "No published hours to continue" : hasUnsaved ? "Save or cancel your changes first" : undefined;

  async function extend() {
    setExtending(true); setExtendError(null);
    try {
      const updated = await adminDoctorsApi.extendHours(doctor.id, extendWeeks);
      onExtended(updated, `${updated.name}'s hours are now published until ${dateLabel(updated.hours_until ?? "")}.`);
    } catch (e) { setExtendError(e instanceof ApiError ? e.message : "The hours could not be extended."); }
    finally { setExtending(false); }
  }

  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-md border border-line bg-sunken px-3.5 py-3">
        {extendError ? <Alert tone="danger" title="Not extended">{extendError}</Alert> : null}
        <p className="text-sm text-fg-muted">
          Published until <span className="font-medium text-fg">{doctor.hours_until ? dateLabel(doctor.hours_until) : "–"}</span>.
          Extending repeats the last published week, day by day.
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Extend by" htmlFor="hp-extend">
            <Select id="hp-extend" value={extendWeeks} onChange={(e) => setExtendWeeks(Number(e.target.value))} disabled={!!blocked}>
              {WEEK_OPTIONS.map((w) => <option key={w} value={w}>{w} weeks</option>)}
            </Select>
          </Field>
          <Button variant="secondary" icon={<Icons.calendar size={16} />} onClick={extend} loading={extending}
            disabled={!!blocked} title={blocked}>Extend hours</Button>
        </div>
        {hasUnsaved && doctor.can_extend ? <p className="text-xs text-fg-subtle">Save or cancel your changes first to extend.</p> : null}
      </section>

      <section className="space-y-3">
        <p className="text-sm font-medium">Change hours</p>
        {doctor.hours.length > 1 ? (
          <Alert tone="info" title="Hours currently differ by day">
            This form sets one set of times for every day you pick. It starts from their first group of days.
          </Alert>
        ) : null}
        <HoursFields value={draft} onChange={onChange} today={today} error={error} idPrefix="hp" startLabel="New hours from" />
      </section>
    </div>
  );
}

/** The review shown before Save when the hours changed: what patients will see. Held patient
 * times the new hours would leave out block the save (the server refuses it too). */
export function HoursReview({ preview, startDate }: { preview: HoursChangePreview; startDate: string }) {
  return (
    <section className="space-y-4">
      {preview.problems.length ? (
        <Alert tone="warning" title="Fix these before saving">
          <ul className="list-disc pl-4">{preview.problems.map((p) => <li key={p}>{p}</li>)}</ul>
        </Alert>
      ) : preview.held_outside.length ? (
        <Alert tone="danger" title={`Can't save: ${preview.held_outside.length} patient time${preview.held_outside.length === 1 ? "" : "s"} fall outside the new hours`}>
          <p>These patients already hold a time with this doctor. Go back and keep these times inside the new hours, or start the new hours after them.</p>
          <ul className="mt-1.5 list-disc pl-4 tabular-nums">{preview.held_outside.map((t) => <li key={t}>{heldLabel(t)}</li>)}</ul>
        </Alert>
      ) : (
        <Alert tone="success" title="New hours look good">No patient&apos;s held time falls outside them.</Alert>
      )}
      <div>
        <p className="mb-1.5 text-sm font-medium">What patients will see</p>
        {preview.hours.length ? <DoctorHours hours={preview.hours} /> : <p className="text-xs text-fg-subtle">No hours fall in the first two weeks.</p>}
      </div>
      {preview.hours_until ? (
        <p className="text-sm text-fg-muted">From <span className="font-medium text-fg">{dateLabel(startDate)}</span> until <span className="font-medium text-fg">{dateLabel(preview.hours_until)}</span>; earlier days stay as they are.</p>
      ) : null}
    </section>
  );
}
