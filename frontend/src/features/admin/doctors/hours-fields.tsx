"use client";

import { cn } from "@/lib/utils";
import { Button, Field, IconButton, Icons, Input, Select } from "@/components/ui";
import { DoctorHours } from "@/features/scheduling/doctor-hours";

const WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const WEEK_OPTIONS = [4, 8, 12, 26];
const MAX_RANGES = 3;

/** A weekly pattern of consulting hours, published for `weeks` weeks from `start_date`. */
export interface HoursDraft { days: string[]; ranges: [string, string][]; start_date: string; weeks: number }

/** Ranges in start order, the way the server stores and shows them. */
export const sortedRanges = (ranges: [string, string][]): [string, string][] =>
  [...ranges].sort(([a], [b]) => a.localeCompare(b));

/** What's wrong with the pattern before it is worth asking the server; the server re-checks everything. */
export function hoursIssue(d: HoursDraft): string | null {
  if (!d.days.length) return "Pick at least one working day";
  if (d.ranges.some(([s, e]) => !s || !e || e <= s)) return "Each range must end after it starts";
  const sorted = sortedRanges(d.ranges);
  if (sorted.some(([s], i) => i > 0 && s < sorted[i - 1][1])) return "Time ranges overlap";
  return null;
}

export function HoursFields({ value, onChange, today, error, idPrefix, startLabel = "Starting", weeksHint }: {
  value: HoursDraft; onChange: (patch: Partial<HoursDraft>) => void; today: string; error: string | null;
  idPrefix: string; startLabel?: string; weeksHint?: string;
}) {
  const issue = hoursIssue(value);
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_auto]">
      <div className="space-y-4">
        <div>
          <p className="mb-1.5 text-sm font-medium">Working days</p>
          <div className="flex flex-wrap gap-1" role="group" aria-label="Working days">
            {WEEK.map((day) => {
              const on = value.days.includes(day);
              return (
                <button key={day} type="button" aria-pressed={on}
                  onClick={() => onChange({ days: on ? value.days.filter((x) => x !== day) : WEEK.filter((x) => x === day || value.days.includes(x)) })}
                  className={cn("h-8 w-11 rounded-sm text-xs font-medium uppercase transition-colors", on ? "bg-brand text-brand-fg" : "bg-sunken text-fg-muted hover:text-fg")}>
                  {day}
                </button>
              );
            })}
          </div>
        </div>
        <div>
          <p className="mb-1.5 text-sm font-medium">Time ranges <span className="font-normal text-fg-subtle">(clinic time)</span></p>
          <div className="space-y-2">
            {value.ranges.map(([start, end], i) => (
              <div key={i} className="flex items-center gap-2">
                <Input type="time" step={1800} aria-label={`Range ${i + 1} start`} className="h-9 w-32 tabular-nums" value={start}
                  onChange={(e) => onChange({ ranges: value.ranges.map((r, j) => (j === i ? [e.target.value, r[1]] : r)) })} />
                <span className="text-fg-subtle" aria-hidden>–</span>
                <Input type="time" step={1800} aria-label={`Range ${i + 1} end`} className="h-9 w-32 tabular-nums" value={end}
                  onChange={(e) => onChange({ ranges: value.ranges.map((r, j) => (j === i ? [r[0], e.target.value] : r)) })} />
                <IconButton size="sm" label="Remove range" icon={<Icons.trash size={14} />} disabled={value.ranges.length === 1}
                  onClick={() => onChange({ ranges: value.ranges.filter((_, j) => j !== i) })} />
              </div>
            ))}
          </div>
          {value.ranges.length < MAX_RANGES ? (
            <Button size="sm" variant="ghost" className="mt-2" icon={<Icons.plus size={14} />}
              onClick={() => onChange({ ranges: [...value.ranges, ["", ""]] })}>Add range</Button>
          ) : null}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={startLabel} required htmlFor={`${idPrefix}-start`}>
            <Input id={`${idPrefix}-start`} type="date" min={today} value={value.start_date} onChange={(e) => onChange({ start_date: e.target.value })} />
          </Field>
          <Field label="Publish for" required htmlFor={`${idPrefix}-weeks`} hint={weeksHint}>
            <Select id={`${idPrefix}-weeks`} value={value.weeks} onChange={(e) => onChange({ weeks: Number(e.target.value) })}>
              {WEEK_OPTIONS.map((w) => <option key={w} value={w}>{w} weeks</option>)}
            </Select>
          </Field>
        </div>
        {error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}
      </div>
      <div>
        <p className="mb-1.5 text-sm font-medium">What patients will see</p>
        {!issue ? (
          <DoctorHours hours={[{ days: value.days, times: sortedRanges(value.ranges) }]} />
        ) : <p className="text-xs text-fg-subtle">Pick days and valid times to preview.</p>}
      </div>
    </div>
  );
}
