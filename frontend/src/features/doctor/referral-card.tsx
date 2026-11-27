"use client";

import Link from "next/link";
import { useState } from "react";
import { casesApi, type CaseDetail, type Department, type Referral, type ReferralUrgency, type RosterDoctor } from "@/lib/api";
import { Badge, Button, Card, CardBody, CardHeader, Field, Icons, Segmented, Select, Textarea, useToast } from "@/components/ui";
import { formatDateTime } from "@/lib/utils";
import { CredentialFields, useClinicianCredentials } from "@/features/doctor/credential-fields";
import type { Me } from "@/features/doctor/use-doctor";

const STATUS: Record<Referral["status"], { label: string; tone: "neutral" | "brand" | "success" | "warning" | "danger" }> = {
  awaiting_time: { label: "Patient to pick a time", tone: "warning" },
  booked: { label: "Booked", tone: "brand" },
  seen: { label: "Seen", tone: "success" },
  completed: { label: "Completed", tone: "success" },
  cancelled: { label: "Cancelled", tone: "danger" },
};

const URGENCY: Array<{ value: ReferralUrgency; label: string }> = [
  { value: "routine", label: "Routine" },
  { value: "soon", label: "Within a week" },
  { value: "urgent", label: "Urgent" },
];

/** Refer the patient on to another department. Signing books the referred visit straight away
 * (backend services/referral_service); the patient can change the time from their portal. */
export function ReferralCard({ detail, me, departments, doctors, onDone }: {
  detail: CaseDetail; me: Me; departments: Department[]; doctors: RosterDoctor[]; onDone: () => Promise<void>;
}) {
  const made = detail.referrals_made ?? [];
  const signed = detail.consultation_notes.length > 0;
  const [open, setOpen] = useState(false);
  const [departmentId, setDepartmentId] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [reason, setReason] = useState("");
  const [question, setQuestion] = useState("");
  const [urgency, setUrgency] = useState<ReferralUrgency>("routine");
  const [busy, setBusy] = useState(false);
  const { credentials, setCredentials, missing, clearPassword } = useClinicianCredentials(me.username);
  const toast = useToast();

  // Only departments someone can actually see the patient in.
  const staffed = departments.filter((d) => doctors.some((doc) => doc.department_id === d.id));
  const inDepartment = doctors.filter((d) => d.department_id === departmentId && d.id !== me.id);
  const ready = departmentId && reason.trim().length >= 3 && !missing;

  async function submit() {
    setBusy(true);
    try {
      await casesApi.refer(detail.case_id, {
        doctor_username: credentials.username, doctor_password: credentials.password,
        to_department_id: departmentId, to_doctor_id: doctorId || null,
        reason: reason.trim(), question: question.trim() || null, urgency,
      });
      clearPassword();
      setOpen(false);
      setDepartmentId(""); setDoctorId(""); setReason(""); setQuestion(""); setUrgency("routine");
      toast.push({ tone: "success", message: "Referred and booked. The patient can see it under My visits." });
      await onDone();
    } catch (err) {
      toast.push({ tone: "danger", message: err instanceof Error ? err.message : "Could not refer the patient." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title={<span className="flex items-center gap-2"><Icons.arrowRight size={16} className="text-brand" />Referrals</span>}
        description="Send the patient to a doctor in another department. Your signed report, their history and uploads go with them, and the visit is booked straight away."
        action={!open && detail.status !== "REJECTED" ? (
          <Button size="sm" variant="secondary" icon={<Icons.plus size={14} />} disabled={!signed} onClick={() => setOpen(true)}
            title={signed ? undefined : "Sign your consultation report first"}>
            Refer patient
          </Button>
        ) : null}
      />
      <CardBody className="space-y-4">
        {!signed && !made.length ? (
          <p className="text-sm text-fg-muted">Sign your consultation report first, so the next doctor has your findings.</p>
        ) : null}

        {made.length ? (
          <ul className="divide-y divide-line rounded-md border border-line">
            {made.map((r) => <MadeRow key={r.id} r={r} />)}
          </ul>
        ) : null}

        {open ? (
          <div className="space-y-4 rounded-md border border-line bg-sunken/40 p-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Department" htmlFor="referral-department" required>
                <Select id="referral-department" value={departmentId}
                  onChange={(e) => { setDepartmentId(e.target.value); setDoctorId(""); }}>
                  <option value="">Choose a department</option>
                  {staffed.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </Select>
              </Field>
              <Field label="Doctor" htmlFor="referral-doctor" hint="Leave as any to book the earliest free doctor.">
                <Select id="referral-doctor" value={doctorId} disabled={!departmentId} onChange={(e) => setDoctorId(e.target.value)}>
                  <option value="">Any doctor (earliest free time)</option>
                  {inDepartment.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </Select>
              </Field>
            </div>
            <Field label="Reason for referral" htmlFor="referral-reason" required>
              <Textarea id="referral-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. Exertional chest tightness with ST changes on ECG" />
            </Field>
            <Field label="Question for the specialist" htmlFor="referral-question" hint="Optional: what you want answered.">
              <Textarea id="referral-question" rows={2} value={question} onChange={(e) => setQuestion(e.target.value)}
                placeholder="e.g. Please evaluate for stable angina and advise on management" />
            </Field>
            <div className="space-y-1.5">
              <p className="text-sm font-medium">How soon</p>
              <Segmented label="How soon" value={urgency} onChange={setUrgency} options={URGENCY} />
              <p className="text-xs text-fg-subtle">Shown to the specialist. The visit&rsquo;s priority still comes from the clinic&rsquo;s triage rules.</p>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
              <CredentialFields idPrefix="referral" value={credentials} onChange={setCredentials}
                hint="Your hospital password" signingInAs={me.name} disabled={busy} />
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button>
                <Button size="sm" onClick={submit} loading={busy} disabled={!ready}>Refer and book</Button>
              </div>
            </div>
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

function MadeRow({ r }: { r: Referral }) {
  const s = STATUS[r.status];
  return (
    <li className="space-y-1.5 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{r.to_department_name}</span>
        {r.doctor_name ? <span className="text-sm text-fg-muted">· {r.doctor_name}</span> : null}
        <Badge tone={s.tone}>{s.label}</Badge>
        {r.urgency !== "routine" ? <Badge tone={r.urgency === "urgent" ? "danger" : "warning"}>{r.urgency === "urgent" ? "Urgent" : "Within a week"}</Badge> : null}
        <Link href={`/cases/${r.case_id}`} className="ml-auto text-sm font-medium text-brand hover:underline">Open visit</Link>
      </div>
      <p className="text-sm text-fg-muted">{r.reason}</p>
      {r.appointment_start && r.status === "booked" ? (
        <p className="text-xs text-fg-subtle" suppressHydrationWarning>Appointment {formatDateTime(r.appointment_start)}</p>
      ) : null}
      {r.outcome_diagnosis || r.outcome_advice ? (
        <div className="rounded-md bg-success-soft/40 p-2.5 text-sm">
          <p className="text-xs font-medium text-fg-muted">{r.outcome_by ?? "Specialist"} signed</p>
          {r.outcome_diagnosis ? <p><span className="text-fg-muted">Diagnosis:</span> {r.outcome_diagnosis}</p> : null}
          {r.outcome_advice ? <p><span className="text-fg-muted">Advice:</span> {r.outcome_advice}</p> : null}
        </div>
      ) : null}
    </li>
  );
}
