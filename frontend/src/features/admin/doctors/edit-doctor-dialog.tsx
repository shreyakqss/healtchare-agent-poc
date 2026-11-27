"use client";

import { useState } from "react";
import { adminDoctorsApi, ApiError } from "@/lib/api";
import type { AdminDoctor, DoctorDepartmentOption, DoctorDetails, HoursChangePreview, UpdateDoctorRequest } from "@/lib/api/types";
import { Alert, Button, Dialog, Field, Icons, Input, KeyValue, SectionTitle, Select, Tabs } from "@/components/ui";
import { hoursIssue, sortedRanges, type HoursDraft } from "@/features/admin/doctors/hours-fields";
import { HoursPanel, HoursReview, dateLabel, hoursDraftFrom } from "@/features/admin/doctors/hours-panel";

type Tab = "details" | "hours";
const TABS: Array<{ id: Tab; label: string }> = [{ id: "details", label: "Details" }, { id: "hours", label: "Hours" }];

/** Admin > Doctors > Edit. Name, NPI, username and department were fixed at onboarding and are
 * shown, not edited; the specialty can change within the department. Both tabs keep their edits
 * and one Save writes whatever changed, reviewing new hours first. */
export function EditDoctorDialog({ doctor, details, departments, today, onClose, onSaved }: {
  doctor: AdminDoctor; details: DoctorDetails; departments: DoctorDepartmentOption[]; today: string;
  onClose: () => void; onSaved: (doctor: AdminDoctor, message: string) => void;
}) {
  const [initialDetails] = useState<UpdateDoctorRequest>(() => ({
    title: details.title, email: details.email, phone: details.phone, licence: details.licence, specialty_code: details.specialty_code,
  }));
  const [initialHours] = useState<HoursDraft>(() => hoursDraftFrom(doctor, today));
  const [tab, setTab] = useState<Tab>("details");
  const [draft, setDraft] = useState<UpdateDoctorRequest>(initialDetails);
  const [hours, setHours] = useState<HoursDraft>(initialHours);
  const [review, setReview] = useState<HoursChangePreview | null>(null);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (patch: Partial<UpdateDoctorRequest>) => setDraft((d) => ({ ...d, ...patch }));
  const department = departments.find((d) => d.department_id === details.department_id);
  const specialties = department?.specialties ?? [];
  const detailsChanged = JSON.stringify(draft) !== JSON.stringify(initialDetails);
  const hoursChanged = JSON.stringify(hours) !== JSON.stringify(initialHours);
  const emailIssue = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(draft.email) ? null : "Enter a valid email";
  const hoursProblem = hoursChanged ? hoursIssue(hours) : null;
  const hoursBody = () => ({ ...hours, ranges: sortedRanges(hours.ranges) });
  const msg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

  function close() { if (!busy) onClose(); }

  async function save() {
    setTouched(true); setError(null);
    if (!detailsChanged && !hoursChanged) { onClose(); return; }
    if (emailIssue) { setTab("details"); return; }
    if (hoursProblem) { setTab("hours"); return; }
    if (hoursChanged && !review) {
      // New hours are reviewed before anything is written.
      setBusy(true);
      try { setReview(await adminDoctorsApi.previewHours(doctor.id, hoursBody())); }
      catch (e) { setError(msg(e, "Could not check the new hours.")); }
      finally { setBusy(false); }
      return;
    }
    await commit();
  }

  async function commit() {
    setBusy(true); setError(null);
    let updated: AdminDoctor | null = null;
    try {
      if (detailsChanged) updated = await adminDoctorsApi.update(doctor.id, draft);
    } catch (e) {
      setError(msg(e, "The details could not be saved. Nothing was changed."));
      setReview(null); setBusy(false);
      return;
    }
    try {
      if (hoursChanged) updated = await adminDoctorsApi.changeHours(doctor.id, hoursBody());
    } catch (e) {
      // Details (if any) are already saved; say so, and keep the dialog open for the hours.
      setError(`${detailsChanged ? "Details were saved, but the hours were not. " : ""}${msg(e, "The hours could not be changed.")}`);
      setReview(null); setBusy(false);
      return;
    }
    setBusy(false);
    const what = detailsChanged && hoursChanged ? "details and hours were" : detailsChanged ? "details were" : "hours were";
    const until = hoursChanged && updated?.hours_until ? ` Hours are published until ${dateLabel(updated.hours_until)}.` : "";
    if (updated) onSaved(updated, `${updated.name}'s ${what} saved.${until}`);
  }

  const footer = review ? (
    <>
      <Button variant="secondary" onClick={() => setReview(null)} disabled={busy} icon={<Icons.arrowLeft size={16} />}>Back</Button>
      <Button onClick={commit} loading={busy} disabled={!!review.problems.length || !!review.held_outside.length} icon={<Icons.check size={16} />}>Confirm and save</Button>
    </>
  ) : (
    <>
      <Button variant="secondary" onClick={close} disabled={busy}>Cancel</Button>
      <Button onClick={save} loading={busy} icon={<Icons.check size={16} />}>
        {hoursChanged ? "Review and save" : "Save changes"}
      </Button>
    </>
  );

  return (
    <Dialog open onClose={close} size="lg" title={review ? "Confirm new hours" : "Edit doctor"} description={doctor.name} footer={footer}>
      {error ? <Alert tone="danger" title="Not saved" className="mb-4">{error}</Alert> : null}

      {review ? (
        <div className="space-y-4">
          {detailsChanged ? <p className="text-sm text-fg-muted">Your detail changes will be saved together with these hours.</p> : null}
          <HoursReview preview={review} startDate={hours.start_date} />
        </div>
      ) : (
        <>
          <Tabs<Tab> idPrefix="edit-doctor" className="mb-5" value={tab} onChange={setTab}
            tabs={TABS.map((t) => ({ ...t, label: (t.id === "details" ? detailsChanged : hoursChanged) ? `${t.label} •` : t.label }))} />

          {/* Both panels stay mounted so switching tabs never drops an edit. */}
          <div role="tabpanel" id="edit-doctor-panel-hours" aria-labelledby="edit-doctor-tab-hours" hidden={tab !== "hours"}>
            <HoursPanel doctor={doctor} today={today} draft={hours} onChange={(patch) => setHours((h) => ({ ...h, ...patch }))}
              error={touched ? hoursProblem : null} hasUnsaved={detailsChanged || hoursChanged} onExtended={onSaved} />
          </div>

          <div role="tabpanel" id="edit-doctor-panel-details" aria-labelledby="edit-doctor-tab-details" hidden={tab !== "details"}>
            <div className="space-y-6">
              <section className="space-y-3">
                <SectionTitle>Fixed at onboarding</SectionTitle>
                <KeyValue columns={2} items={[
                  { label: "Name", value: doctor.name },
                  { label: "NPI", value: <span className="font-mono">{doctor.npi}</span> },
                  { label: "Username", value: <span className="font-mono">{doctor.username}</span> },
                  { label: "Department", value: department?.department_name ?? details.department_id ?? "Not routed" },
                ]} />
              </section>

              <section className="space-y-3">
                <SectionTitle>Contact</SectionTitle>
                <div className="grid gap-3 sm:grid-cols-[96px_1fr_1fr]">
                  <Field label="Title" htmlFor="ed-title"><Input id="ed-title" value={draft.title} onChange={(e) => set({ title: e.target.value })} /></Field>
                  <Field label="Email" required htmlFor="ed-email" error={touched ? emailIssue : null} hint="Also their CareFlow login email.">
                    <Input id="ed-email" type="email" autoComplete="off" value={draft.email} onChange={(e) => set({ email: e.target.value.trim() })} />
                  </Field>
                  <Field label="Phone" htmlFor="ed-phone"><Input id="ed-phone" type="tel" value={draft.phone} onChange={(e) => set({ phone: e.target.value })} /></Field>
                </div>
              </section>

              <section className="space-y-3">
                <SectionTitle>Professional</SectionTitle>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Specialty" required htmlFor="ed-specialty"
                    hint={specialties.length > 1 ? "Only specialties within their department." : "Their department has one specialty."}>
                    <Select id="ed-specialty" value={draft.specialty_code} disabled={specialties.length <= 1}
                      onChange={(e) => set({ specialty_code: e.target.value })}>
                      {specialties.some((s) => s.code === draft.specialty_code) ? null : <option value={draft.specialty_code}>{draft.specialty_code}</option>}
                      {specialties.map((s) => <option key={s.code} value={s.code}>{s.title} ({s.code})</option>)}
                    </Select>
                  </Field>
                  <Field label="Licence number" htmlFor="ed-licence"><Input id="ed-licence" value={draft.licence} onChange={(e) => set({ licence: e.target.value })} /></Field>
                </div>
              </section>
            </div>
          </div>
        </>
      )}
    </Dialog>
  );
}
