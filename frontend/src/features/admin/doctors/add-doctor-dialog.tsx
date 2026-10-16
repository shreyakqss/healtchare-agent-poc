"use client";

import { useState } from "react";
import { adminDoctorsApi, ApiError } from "@/lib/api";
import type { AdminDoctor, DoctorDepartmentOption, DoctorPreview, NewDoctorRequest } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { Alert, Button, Dialog, Field, IconButton, Icons, Input, KeyValue, SectionTitle, Select } from "@/components/ui";
import { DoctorHours } from "@/features/scheduling/doctor-hours";

const WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const WEEK_OPTIONS = [4, 8, 12, 26];
const MAX_RANGES = 3;

type Draft = NewDoctorRequest;

function emptyDraft(departments: DoctorDepartmentOption[], today: string): Draft {
  const first = departments.find((d) => d.specialties.length) ?? departments[0];
  return {
    title: "Dr.", first_name: "", last_name: "", email: "", phone: "", username: "", password: "",
    npi: "", department_id: first?.department_id ?? "", specialty_code: first?.specialties[0]?.code ?? "", licence: "",
    days: ["mon", "tue", "wed", "thu", "fri"], ranges: [["10:00", "13:00"], ["16:00", "19:00"]], start_date: today, weeks: 12,
  };
}

/** What's wrong with the draft before it is worth asking the server; the server re-checks everything. */
type IssueKey = keyof Draft | "confirm" | "hours";

function draftIssues(d: Draft, confirm: string): Partial<Record<IssueKey, string>> {
  const issues: Partial<Record<IssueKey, string>> = {};
  if (!d.first_name.trim()) issues.first_name = "Required";
  if (!d.last_name.trim()) issues.last_name = "Required";
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(d.email)) issues.email = "Enter a valid email";
  if (!/^[a-z][a-z0-9._-]{2,31}$/.test(d.username)) issues.username = "3-32 lowercase letters, numbers, . _ -; starts with a letter";
  if (d.password.length < 9) issues.password = "At least 9 characters";
  if (confirm !== d.password) issues.confirm = "Passwords do not match";
  if (!/^\d{10}$/.test(d.npi)) issues.npi = "10 digits";
  if (!d.specialty_code) issues.specialty_code = "Pick a specialty";
  if (!d.days.length) issues.hours = "Pick at least one working day";
  else if (d.ranges.some(([s, e]) => !s || !e || e <= s)) issues.hours = "Each range must end after it starts";
  else {
    const sorted = [...d.ranges].sort(([a], [b]) => a.localeCompare(b));
    if (sorted.some(([s], i) => i > 0 && s < sorted[i - 1][1])) issues.hours = "Time ranges overlap";
  }
  return issues;
}

export function AddDoctorDialog({ open, onClose, onCreated, clinic, departments }: {
  open: boolean; onClose: () => void; onCreated: (doctor: AdminDoctor) => void;
  clinic: { id: string; name: string; today: string }; departments: DoctorDepartmentOption[];
}) {
  const [draft, setDraft] = useState<Draft>(() => emptyDraft(departments, clinic.today));
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState(false);
  const [step, setStep] = useState<"form" | "review">("form");
  const [preview, setPreview] = useState<DoctorPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const issues = draftIssues(draft, confirm);
  const show = (key: IssueKey) => (touched ? issues[key] ?? null : null);
  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));
  const department = departments.find((d) => d.department_id === draft.department_id);
  const specialtyTitle = department?.specialties.find((s) => s.code === draft.specialty_code)?.title;
  const body = (): NewDoctorRequest => ({ ...draft, ranges: [...draft.ranges].sort(([a], [b]) => a.localeCompare(b)) });

  function close() {
    if (busy) return;
    setDraft(emptyDraft(departments, clinic.today)); setConfirm(""); setTouched(false); setStep("form"); setPreview(null); setError(null);
    onClose();
  }
  async function review() {
    setTouched(true);
    if (Object.keys(issues).length) return;
    setBusy(true); setError(null);
    try { setPreview(await adminDoctorsApi.preview(body())); setStep("review"); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not check the details."); }
    finally { setBusy(false); }
  }
  async function create() {
    setBusy(true); setError(null);
    try {
      const doctor = await adminDoctorsApi.create(body());
      setBusy(false);
      setDraft(emptyDraft(departments, clinic.today)); setConfirm(""); setTouched(false); setStep("form"); setPreview(null);
      onCreated(doctor);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The doctor could not be created. Nothing was saved.");
      setBusy(false);
    }
  }

  const footer = step === "form" ? (
    <>
      <Button variant="secondary" onClick={close} disabled={busy}>Cancel</Button>
      <Button onClick={review} loading={busy} iconRight={<Icons.arrowRight size={16} />}>Review</Button>
    </>
  ) : (
    <>
      <Button variant="secondary" onClick={() => { setStep("form"); setError(null); }} disabled={busy} icon={<Icons.arrowLeft size={16} />}>Back</Button>
      <Button onClick={create} loading={busy} disabled={!!preview?.problems.length} icon={<Icons.check size={16} />}>Create doctor</Button>
    </>
  );

  return (
    <Dialog open={open} onClose={close} size="lg" title="Add doctor"
      description={`Creates the doctor at ${clinic.name}: hospital-system record, consulting hours and CareFlow login.`} footer={footer}>
      {error ? <Alert tone="danger" title="Not saved" className="mb-4">{error}</Alert> : null}

      {step === "form" ? (
        <div className="space-y-6">
          <section className="space-y-3">
            <SectionTitle>Personal</SectionTitle>
            <div className="grid gap-3 sm:grid-cols-[96px_1fr_1fr]">
              <Field label="Title" htmlFor="d-title"><Input id="d-title" value={draft.title} onChange={(e) => set({ title: e.target.value })} /></Field>
              <Field label="First name" required htmlFor="d-first" error={show("first_name")}><Input id="d-first" value={draft.first_name} onChange={(e) => set({ first_name: e.target.value })} /></Field>
              <Field label="Last name" required htmlFor="d-last" error={show("last_name")}><Input id="d-last" value={draft.last_name} onChange={(e) => set({ last_name: e.target.value })} /></Field>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Email" required htmlFor="d-email" error={show("email")}><Input id="d-email" type="email" autoComplete="off" value={draft.email} onChange={(e) => set({ email: e.target.value.trim() })} /></Field>
              <Field label="Phone" htmlFor="d-phone"><Input id="d-phone" type="tel" value={draft.phone} onChange={(e) => set({ phone: e.target.value })} /></Field>
            </div>
          </section>

          <section className="space-y-3">
            <SectionTitle>Login</SectionTitle>
            <Field label="Username" required htmlFor="d-username" error={show("username")}
              hint="Used for both CareFlow and the hospital system. Lowercase, cannot be changed later.">
              <Input id="d-username" autoComplete="off" className="font-mono" value={draft.username}
                onChange={(e) => set({ username: e.target.value.toLowerCase().replace(/\s/g, "") })} />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Password" required htmlFor="d-password" error={show("password")} hint="9+ characters with three of: lowercase, uppercase, number, symbol.">
                <Input id="d-password" type="password" autoComplete="new-password" value={draft.password} onChange={(e) => set({ password: e.target.value })} />
              </Field>
              <Field label="Confirm password" required htmlFor="d-confirm" error={show("confirm")}>
                <Input id="d-confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
              </Field>
            </div>
          </section>

          <section className="space-y-3">
            <SectionTitle>Professional</SectionTitle>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Department" required htmlFor="d-dept" hint="Patients with matching complaints are routed here.">
                <Select id="d-dept" value={draft.department_id}
                  onChange={(e) => {
                    const next = departments.find((d) => d.department_id === e.target.value);
                    set({ department_id: e.target.value, specialty_code: next?.specialties[0]?.code ?? "" });
                  }}>
                  {departments.map((d) => <option key={d.department_id} value={d.department_id} disabled={!d.specialties.length}>{d.department_name}</option>)}
                </Select>
              </Field>
              <Field label="Specialty" required htmlFor="d-specialty" error={show("specialty_code")}>
                <Select id="d-specialty" value={draft.specialty_code} onChange={(e) => set({ specialty_code: e.target.value })}>
                  {(department?.specialties ?? []).map((s) => <option key={s.code} value={s.code}>{s.title} ({s.code})</option>)}
                </Select>
              </Field>
              <Field label="NPI" required htmlFor="d-npi" error={show("npi")} hint="10-digit National Provider Identifier.">
                <Input id="d-npi" inputMode="numeric" maxLength={10} className="font-mono" value={draft.npi}
                  onChange={(e) => set({ npi: e.target.value.replace(/\D/g, "") })} />
              </Field>
              <Field label="Licence number" htmlFor="d-licence"><Input id="d-licence" value={draft.licence} onChange={(e) => set({ licence: e.target.value })} /></Field>
            </div>
          </section>

          <section className="space-y-3">
            <SectionTitle>Consulting hours</SectionTitle>
            <div className="grid gap-5 lg:grid-cols-[1fr_auto]">
              <div className="space-y-4">
                <div>
                  <p className="mb-1.5 text-sm font-medium">Working days</p>
                  <div className="flex flex-wrap gap-1" role="group" aria-label="Working days">
                    {WEEK.map((day) => {
                      const on = draft.days.includes(day);
                      return (
                        <button key={day} type="button" aria-pressed={on}
                          onClick={() => set({ days: on ? draft.days.filter((x) => x !== day) : WEEK.filter((x) => x === day || draft.days.includes(x)) })}
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
                    {draft.ranges.map(([start, end], i) => (
                      <div key={i} className="flex items-center gap-2">
                        <Input type="time" step={1800} aria-label={`Range ${i + 1} start`} className="h-9 w-32 tabular-nums" value={start}
                          onChange={(e) => set({ ranges: draft.ranges.map((r, j) => (j === i ? [e.target.value, r[1]] : r)) })} />
                        <span className="text-fg-subtle" aria-hidden>–</span>
                        <Input type="time" step={1800} aria-label={`Range ${i + 1} end`} className="h-9 w-32 tabular-nums" value={end}
                          onChange={(e) => set({ ranges: draft.ranges.map((r, j) => (j === i ? [r[0], e.target.value] : r)) })} />
                        <IconButton size="sm" label="Remove range" icon={<Icons.trash size={14} />} disabled={draft.ranges.length === 1}
                          onClick={() => set({ ranges: draft.ranges.filter((_, j) => j !== i) })} />
                      </div>
                    ))}
                  </div>
                  {draft.ranges.length < MAX_RANGES ? (
                    <Button size="sm" variant="ghost" className="mt-2" icon={<Icons.plus size={14} />}
                      onClick={() => set({ ranges: [...draft.ranges, ["", ""]] })}>Add range</Button>
                  ) : null}
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Starting" required htmlFor="d-start">
                    <Input id="d-start" type="date" min={clinic.today} value={draft.start_date} onChange={(e) => set({ start_date: e.target.value })} />
                  </Field>
                  <Field label="Publish for" required htmlFor="d-weeks" hint="Extend later from the doctors list.">
                    <Select id="d-weeks" value={draft.weeks} onChange={(e) => set({ weeks: Number(e.target.value) })}>
                      {WEEK_OPTIONS.map((w) => <option key={w} value={w}>{w} weeks</option>)}
                    </Select>
                  </Field>
                </div>
                {show("hours") ? <p role="alert" className="text-xs text-danger">{show("hours")}</p> : null}
              </div>
              <div>
                <p className="mb-1.5 text-sm font-medium">What patients will see</p>
                {draft.days.length && !issues.hours ? (
                  <DoctorHours hours={[{ days: draft.days, times: [...draft.ranges].sort(([a], [b]) => a.localeCompare(b)) }]} />
                ) : <p className="text-xs text-fg-subtle">Pick days and valid times to preview.</p>}
              </div>
            </div>
          </section>
        </div>
      ) : preview ? (
        <div className="space-y-5">
          {preview.problems.length ? (
            <Alert tone="warning" title="Fix these before creating the doctor">
              <ul className="list-disc pl-4">{preview.problems.map((p) => <li key={p}>{p}</li>)}</ul>
            </Alert>
          ) : (
            <Alert tone="success" title="Ready to create">All details checked against the hospital system and the login system.</Alert>
          )}
          <KeyValue columns={2} items={[
            { label: "Doctor", value: `${draft.title} ${draft.first_name} ${draft.last_name}`.trim() },
            { label: "Hospital", value: preview.clinic.name },
            { label: "Department", value: department?.department_name },
            { label: "Specialty", value: specialtyTitle ? `${specialtyTitle} (${draft.specialty_code})` : draft.specialty_code },
            { label: "NPI", value: <span className="font-mono">{draft.npi}</span> },
            { label: "Username", value: <span className="font-mono">{draft.username}</span> },
            { label: "Email", value: draft.email },
            { label: "Hours published", value: preview.hours_until ? `${preview.blocks} sessions, until ${preview.hours_until}` : "–" },
          ]} />
          <div>
            <p className="mb-1.5 text-sm font-medium">What patients will see</p>
            {preview.hours.length ? <DoctorHours hours={preview.hours} /> : <p className="text-xs text-fg-subtle">No hours fall in the first two weeks.</p>}
          </div>
          <div className="rounded-md border border-line bg-sunken px-3.5 py-3 text-sm text-fg-muted">
            <p className="mb-1 font-medium text-fg">Creating this doctor will:</p>
            <ul className="list-disc space-y-0.5 pl-4">
              <li>add them to the hospital system with their specialty, so matching patients are routed to them;</li>
              <li>publish their consulting hours as bookable appointment times;</li>
              <li>create their CareFlow doctor login with the password you set.</li>
            </ul>
            <p className="mt-2 text-xs">If any step fails, nothing is kept.</p>
          </div>
        </div>
      ) : null}
    </Dialog>
  );
}
