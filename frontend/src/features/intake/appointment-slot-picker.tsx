"use client";

import { useMemo, useState } from "react";
import { casesApi, type PatientCase, type PatientRouting, type Slot } from "@/lib/api";
import { cn, initials } from "@/lib/utils";
import { Icons } from "@/components/ui/icons";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/feedback";
import { DoctorHours } from "@/features/scheduling/doctor-hours";

const TIME_LABEL = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
const TIMES_PER_DAY = 6;
const DAYS_SHOWN = 2;

function dayKey(iso: string): string {
  return new Date(iso).toDateString();
}

function dayLabel(iso: string): string {
  const d = new Date(iso);
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (d.toDateString() === new Date().toDateString()) return "Today";
  if (d.toDateString() === tomorrow.toDateString()) return "Tomorrow";
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

function when(slot: Slot): string {
  return `${dayLabel(slot.start)}, ${TIME_LABEL.format(new Date(slot.start))}`;
}

interface DoctorTimes { id: string; name: string; slots: Slot[]; next: Slot | null }

/** The patient's appointment, booking-app style: the earliest available doctor first (the
 * default), then every doctor in the department as a card with their next open times. Picking
 * a time only selects it; "Confirm appointment" books that doctor and time straight onto their
 * hospital calendar - no clinician approval (instant booking). Without `doctor_choice`
 * (urgent, or already approved) the times come pre-filtered and the cards are just those times. */
export function AppointmentSlotPicker({ caseId, routing, locked, onUpdated }: {
  caseId: string;
  routing: PatientRouting;
  locked?: boolean;
  onUpdated?: (detail: PatientCase) => void;
}) {
  const toast = useToast();
  const all = useMemo(
    () => (routing.slot_options.length ? routing.slot_options : routing.suggested_slot ? [routing.suggested_slot] : []),
    [routing.slot_options, routing.suggested_slot],
  );
  const current = all.find((s) => s.id === routing.selected_slot_id) ?? null;
  const confirmed = Boolean(routing.slot_confirmed) && current !== null;
  const [pickedId, setPickedId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const doctors = useMemo<DoctorTimes[]>(() => {
    const byDoctor = new Map<string, DoctorTimes>();
    for (const slot of all) {
      const id = slot.practitioner_id;
      const entry = byDoctor.get(id) ?? { id, name: slot.doctor_name ?? routing.doctor_name ?? "Doctor", slots: [], next: null };
      entry.slots.push(slot);
      if (!entry.next && !slot.taken) entry.next = slot;
      byDoctor.set(id, entry);
    }
    // Earliest next time first: the server orders slots earliest-first, less busy doctor first.
    return [...byDoctor.values()].sort((a, b) =>
      (a.next ? new Date(a.next.start).getTime() : Infinity) - (b.next ? new Date(b.next.start).getTime() : Infinity));
  }, [all, routing.doctor_name]);

  const earliest = doctors[0]?.next ?? null;
  const picked = all.find((s) => s.id === pickedId) ?? null;

  if (!all.length) {
    return <p className="text-sm text-fg-subtle">No open time found yet. The clinic will reach out to schedule.</p>;
  }

  async function confirm(slot: Slot) {
    setSaving(true);
    try {
      const updated = await casesApi.selectSlot(caseId, slot.id);
      setPickedId(null);
      onUpdated?.(updated);
      toast.push({ tone: "success", message: `Booked with ${slot.doctor_name ?? "your doctor"}, ${when(slot)}.` });
    } catch (err) {
      setPickedId(null);
      toast.push({ tone: "danger", message: err instanceof Error ? err.message : "Could not book that time." });
    } finally {
      setSaving(false);
    }
  }

  // Booked (or locked): the appointment, with a way to change it while that is still allowed.
  // A booked time that has gone by is fixed too - that visit is over.
  const passed = Boolean(routing.slot_passed) && confirmed;
  const fixed = locked || passed;
  if (fixed || (confirmed && expanded !== "change")) {
    const shown = current ?? routing.suggested_slot;
    return (
      <div className="space-y-3">
        <div className="flex flex-col gap-3 rounded-lg border border-success/40 bg-success-soft px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <Avatar name={routing.doctor_name} />
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-success">
                <Icons.checkCircle size={13} /> {passed ? "Past appointment" : locked ? "Your visit" : "Appointment booked"}
              </p>
              <p className="truncate text-sm font-semibold">{routing.doctor_name ?? "A clinician"} · {routing.department_name}</p>
              {shown ? <p className="text-sm text-fg-muted">{when(shown)}</p> : null}
            </div>
          </div>
          {!fixed ? <Button size="sm" variant="secondary" onClick={() => setExpanded("change")}>Change</Button> : null}
        </div>
        <p className="flex items-center gap-1.5 text-xs text-fg-subtle">
          <Icons.info size={13} className="shrink-0" />
          {passed
            ? "This appointment time has passed. For a new problem, start a new visit from the intake form."
            : locked ? "This time is set for your visit." : "It's on your doctor's calendar. You can change it here if your plans change."}
        </p>
      </div>
    );
  }

  const choosing = Boolean(routing.doctor_choice);

  return (
    <div className="space-y-4">
      {confirmed ? (
        <div className="flex items-center justify-between gap-3 text-sm">
          <p className="text-fg-muted">Pick a new doctor or time, then confirm.</p>
          <Button size="sm" variant="ghost" onClick={() => { setExpanded(null); setPickedId(null); }}>Keep current</Button>
        </div>
      ) : null}

      {earliest ? (
        <section className="rounded-lg border border-brand-ring bg-brand-soft/40 p-4">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-brand">
            <Icons.clock size={13} /> Earliest available
          </p>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-center gap-3">
              <Avatar name={earliest.doctor_name ?? routing.doctor_name} />
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{earliest.doctor_name ?? routing.doctor_name}</p>
                <p className="text-sm text-fg-muted">{routing.department_name} · {when(earliest)}</p>
              </div>
            </div>
            <Button onClick={() => setPickedId(earliest.id)} variant={pickedId === earliest.id ? "primary" : "secondary"}
              icon={pickedId === earliest.id ? <Icons.check size={15} /> : undefined} disabled={saving}>
              {pickedId === earliest.id ? "Selected" : "Choose this"}
            </Button>
          </div>
        </section>
      ) : null}

      {!choosing ? (
        // No doctor choice (urgent, or already approved): the soonest times only, as one list.
        <section className="space-y-2">
          <p className="text-sm font-medium">Other times</p>
          <div className="flex flex-wrap gap-2">
            {all.filter((s) => !s.taken && s.id !== earliest?.id).slice(0, TIMES_PER_DAY).map((slot) => (
              <button key={slot.id} type="button" disabled={saving} onClick={() => setPickedId(slot.id)} aria-pressed={slot.id === pickedId}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[13px] font-medium transition-colors",
                  slot.id === pickedId ? "border-brand bg-brand text-brand-fg" : "border-line bg-surface text-fg hover:border-brand-ring hover:bg-brand-soft",
                )}>
                {slot.id === pickedId ? <Icons.check size={13} /> : null}
                {when(slot)}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {choosing ? <section className="space-y-3">
        <p className="text-sm font-medium">All doctors in {routing.department_name}</p>
        {doctors.map((doctor) => (
          <DoctorCard key={doctor.id} doctor={doctor} pickedId={pickedId} currentId={current?.id ?? null}
            showAll={expanded === doctor.id} onToggle={() => setExpanded(expanded === doctor.id ? null : doctor.id)}
            hours={routing.hours_by_doctor?.[doctor.id] ?? (doctor.id === routing.doctor_id ? routing.doctor_hours : undefined)}
            onPick={(slot) => setPickedId(slot.id)} disabled={saving} />
        ))}
      </section> : null}

      {picked ? (
        <div className="sticky bottom-3 z-10 flex flex-col gap-3 rounded-lg border border-line bg-surface p-4 shadow-card sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-wide text-fg-subtle">Your selection</p>
            <p className="truncate text-sm font-semibold">{picked.doctor_name ?? routing.doctor_name} · {when(picked)}</p>
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => setPickedId(null)} disabled={saving}>Cancel</Button>
            <Button onClick={() => void confirm(picked)} loading={saving} icon={<Icons.check size={15} />}>Confirm appointment</Button>
          </div>
        </div>
      ) : (
        <p className="flex items-center gap-1.5 text-xs text-fg-subtle">
          <Icons.info size={13} className="shrink-0" />
          {confirmed ? "Your current booking stays until you confirm a new one." : "Choose a doctor and time, then confirm to book it."}
        </p>
      )}
    </div>
  );
}

function Avatar({ name }: { name: string | null | undefined }) {
  return (
    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-soft text-sm font-semibold text-brand">
      {initials(name ?? "Doctor")}
    </div>
  );
}

/** One doctor: their next open times for the first couple of days, all of them on "More times". */
function DoctorCard({ doctor, pickedId, currentId, showAll, onToggle, hours, onPick, disabled }: {
  doctor: DoctorTimes; pickedId: string | null; currentId: string | null; showAll: boolean; onToggle: () => void;
  hours?: PatientRouting["doctor_hours"]; onPick: (slot: Slot) => void; disabled: boolean;
}) {
  const days = useMemo(() => {
    const byDay = new Map<string, Slot[]>();
    for (const slot of doctor.slots) byDay.set(dayKey(slot.start), [...(byDay.get(dayKey(slot.start)) ?? []), slot]);
    return [...byDay.values()];
  }, [doctor.slots]);
  const visible = showAll ? days : days.slice(0, DAYS_SHOWN).map((d) => d.slice(0, TIMES_PER_DAY));
  const hidden = doctor.slots.length - visible.reduce((n, d) => n + d.length, 0);

  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar name={doctor.name} />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{doctor.name}</p>
            <p className="text-xs text-fg-muted">{doctor.next ? `Next available: ${when(doctor.next)}` : "No open time right now"}</p>
          </div>
        </div>
        {hours?.length ? <DoctorHours hours={hours} /> : null}
      </div>
      <div className="space-y-2.5">
        {visible.map((slots) => (
          <div key={slots[0].start}>
            <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-fg-subtle">{dayLabel(slots[0].start)}</p>
            <div className="flex flex-wrap gap-2">
              {slots.map((slot) => {
                const picked = slot.id === pickedId;
                const mine = slot.id === currentId && !pickedId;
                const taken = Boolean(slot.taken) && slot.id !== currentId;
                return (
                  <button key={slot.id} type="button" disabled={disabled || taken} onClick={() => onPick(slot)} aria-pressed={picked}
                    title={taken ? "Already booked by another patient" : undefined}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[13px] font-medium transition-colors disabled:cursor-default",
                      picked ? "border-brand bg-brand text-brand-fg"
                        : mine ? "border-brand bg-brand-soft text-brand"
                        : taken ? "cursor-not-allowed border-line bg-sunken text-fg-subtle line-through opacity-60"
                        : "border-line bg-surface text-fg hover:border-brand-ring hover:bg-brand-soft",
                    )}>
                    {picked ? <Icons.check size={13} /> : null}
                    {TIME_LABEL.format(new Date(slot.start))}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      {hidden > 0 || showAll ? (
        <button type="button" onClick={onToggle} className="mt-3 text-xs font-medium text-brand hover:underline">
          {showAll ? "Fewer times" : `More times (${hidden})`}
        </button>
      ) : null}
    </div>
  );
}
