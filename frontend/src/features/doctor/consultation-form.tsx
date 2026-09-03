"use client";

import { useState } from "react";
import { ApiError, casesApi, hospitalApi, type CaseDetail, type HospitalIdentity } from "@/lib/api";
import { Alert, Button, Card, CardBody, CardHeader, Field, Icons, Textarea, useToast } from "@/components/ui";
import { CredentialFields, useClinicianCredentials } from "@/features/doctor/credential-fields";
import type { Me } from "@/features/doctor/use-doctor";

/** Record the consultation, then release the visit summary. Both actions are attributed to
 * a verified HMS login, so each carries the clinician's credentials. */
export function ConsultationForm({ c, me, onDone, hospital }: {
  c: CaseDetail; me: Me; onDone: () => Promise<void>; hospital: HospitalIdentity | null;
}) {
  const hasNote = c.consultation_notes.length > 0;
  const [notes, setNotes] = useState("");
  const [prescription, setPrescription] = useState("");
  const [testsOrdered, setTestsOrdered] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [referralNotes, setReferralNotes] = useState("");
  const { credentials, setCredentials, missing: missingCredentials, clearPassword } = useClinicianCredentials(me.username ?? "");
  const [busy, setBusy] = useState<"note" | "finalize" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  async function saveNote() {
    setBusy("note");
    setError(null);
    try {
      await casesApi.addNote(c.case_id, {
        doctor_username: credentials.username.trim(), doctor_password: credentials.password,
        consultation_mode: "in_person", notes: notes.trim(),
        prescription: prescription.trim() || undefined, follow_up_instructions: followUp.trim() || undefined,
        tests_ordered: testsOrdered.trim() || undefined, referral_notes: referralNotes.trim() || undefined,
      });
      toast.push({ tone: "success", message: "Consultation recorded" });
      clearPassword();
      await onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the consultation.");
    } finally {
      setBusy(null);
    }
  }

  async function finalize() {
    setBusy("finalize");
    setError(null);
    try {
      await casesApi.finalize(c.case_id, { finalizer_username: credentials.username.trim(), finalizer_password: credentials.password });
      toast.push({ tone: "success", message: "Visit summary released" });
      clearPassword();
      await onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not release the visit summary.");
    } finally {
      setBusy(null);
    }
  }

  if (hasNote) {
    const n = c.consultation_notes[c.consultation_notes.length - 1];
    return (
      <Card className="border-brand-ring/40">
        <CardHeader title="Release visit summary" description="The consultation is recorded. Releasing generates the patient's summary and drafts the follow-up task for the HMS." />
        <CardBody className="space-y-4">
          {n.referral_notes ? (
            <div className="rounded-md border border-line bg-sunken/60 px-3.5 py-3 text-sm">
              <p className="text-xs font-medium text-fg-muted">For other doctors (not shown to the patient)</p>
              <p className="mt-1 whitespace-pre-line">{n.referral_notes}</p>
            </div>
          ) : null}
          <ReportDocument patientName={c.demographics.name} doctorName={n.doctor_name}
            notes={n.notes} prescription={n.prescription} testsOrdered={n.tests_ordered}
            followUp={n.follow_up_instructions} hospital={hospital} />
          {error ? <Alert tone="danger">{error}</Alert> : null}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CredentialFields idPrefix="finalizer" value={credentials} onChange={setCredentials}
              signingInAs={me.username ? `${me.name} (${me.username})` : null}
              hint="Verified against the hospital system" />
            <Button loading={busy === "finalize"} disabled={missingCredentials} onClick={finalize} icon={<Icons.send size={16} />}>
              Release visit summary
            </Button>
          </div>
        </CardBody>
      </Card>
    );
  }

  return (
    <Card className="border-brand-ring/40">
      <CardHeader title="Record the consultation" description="Your own words, section by section - left is what you write, right is the document the patient will see." />
      <CardBody className="space-y-4">
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-4">
            <Field label="Consultation notes" required htmlFor="c-notes" hint="Findings, assessment and plan">
              <Textarea id="c-notes" rows={6} value={notes} onChange={(e) => setNotes(e.target.value)} className="min-h-0" />
            </Field>
            <Field label="Prescription" htmlFor="c-rx" hint="Medicines">
              <Textarea id="c-rx" rows={5} value={prescription} onChange={(e) => setPrescription(e.target.value)} className="min-h-0" />
            </Field>
            <Field label="Tests / investigations" htmlFor="c-tests" hint="What to get done">
              <Textarea id="c-tests" rows={5} value={testsOrdered} onChange={(e) => setTestsOrdered(e.target.value)} className="min-h-0" />
            </Field>
            <Field label="Follow-up instructions" htmlFor="c-fu" hint="Becomes the draft follow-up task">
              <Textarea id="c-fu" rows={5} value={followUp} onChange={(e) => setFollowUp(e.target.value)} className="min-h-0" />
            </Field>
            <Field label="Notes for other doctors" htmlFor="c-referral" hint="Referral/handoff notes; clinicians only, never shown to the patient">
              <Textarea id="c-referral" rows={5} value={referralNotes} onChange={(e) => setReferralNotes(e.target.value)} className="min-h-0" />
            </Field>
          </div>

          <ReportDocument patientName={c.demographics.name} doctorName={me.name}
            notes={notes} prescription={prescription} testsOrdered={testsOrdered} followUp={followUp} hospital={hospital} />
        </div>

        {error ? <Alert tone="danger">{error}</Alert> : null}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CredentialFields idPrefix="doctor" value={credentials} onChange={setCredentials}
            signingInAs={me.username ? `${me.name} (${me.username})` : null}
            hint="Verified against the hospital system" />
          <Button loading={busy === "note"} disabled={!notes.trim() || missingCredentials} onClick={saveNote} icon={<Icons.check size={16} />}>Save consultation</Button>
        </div>
      </CardBody>
    </Card>
  );
}

const DOCUMENT_SECTIONS = [
  { key: "notes", label: "Consultation notes" },
  { key: "prescription", label: "Prescription" },
  { key: "testsOrdered", label: "Tests / investigations" },
  { key: "followUp", label: "Follow-up instructions" },
] as const;

/** A live, read-only render of the visit record as the clinic's own letterhead document - what
 * the patient's browser will show, section by section, not a free-text draft. `hospital` is the
 * facility record this app already reads for the clinic's identity elsewhere (OpenEMR first,
 * YAML config as fallback - see GET /hospital/config); with none available the letterhead falls
 * back to a plain label. Referral notes never appear here - clinicians only. */
function ReportDocument({ patientName, doctorName, hospital, ...sections }: {
  patientName: string; doctorName: string | null; hospital: HospitalIdentity | null;
  notes?: string | null; prescription?: string | null; testsOrdered?: string | null; followUp?: string | null;
}) {
  const addressLine = hospital?.address
    ? [hospital.address.line1, hospital.address.city, hospital.address.state, hospital.address.postal_code].filter(Boolean).join(", ")
    : null;
  const contactLine = hospital ? [hospital.phone, hospital.email].filter(Boolean).join(" · ") : null;
  const filled = DOCUMENT_SECTIONS.filter((s) => sections[s.key]?.trim());

  return (
    <div className="rounded-md border border-line bg-surface shadow-card">
      <div className={hospital?.has_letterhead ? "border-b border-line" : "border-b-2 border-brand px-5 py-4"}>
        {hospital?.has_letterhead ? (
          // eslint-disable-next-line @next/next/no-img-element -- the clinic's own uploaded letterhead, not a static import
          <img src={hospitalApi.letterheadUrl(hospital.id)} alt={`${hospital.name} letterhead`} className="w-full object-contain" />
        ) : hospital ? (
          <>
            <p className="text-lg font-bold text-fg">{hospital.name}</p>
            {addressLine ? <p className="mt-0.5 text-xs text-fg-muted">{addressLine}</p> : null}
            {contactLine ? <p className="text-xs text-fg-muted">{contactLine}</p> : null}
          </>
        ) : (
          <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">Visit report</p>
        )}
      </div>
      <div className="max-h-[32rem] min-h-[15.5rem] space-y-4 overflow-y-auto px-5 py-4">
        <dl className="grid grid-cols-2 gap-2 text-xs text-fg-muted">
          <div><dt className="text-fg-subtle">Patient</dt><dd className="font-medium text-fg">{patientName || "Unnamed patient"}</dd></div>
          <div><dt className="text-fg-subtle">Date</dt><dd className="font-medium text-fg" suppressHydrationWarning>{new Date().toLocaleDateString()}</dd></div>
          <div className="col-span-2"><dt className="text-fg-subtle">Clinician</dt><dd className="font-medium text-fg">{doctorName ?? "–"}</dd></div>
        </dl>
        <hr className="border-line" />
        {filled.length ? filled.map((s) => (
          <div key={s.key}>
            <p className="text-xs font-medium text-fg-muted">{s.label}</p>
            <p className="mt-0.5 whitespace-pre-wrap text-[15px] leading-6 text-fg">{sections[s.key]}</p>
          </div>
        )) : <p className="text-sm italic text-fg-subtle">Nothing written yet.</p>}
      </div>
    </div>
  );
}
