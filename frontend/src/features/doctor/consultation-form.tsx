"use client";

import { useState } from "react";
import { ApiError, casesApi, type CaseDetail } from "@/lib/api";
import { Alert, Button, Card, CardBody, CardHeader, Field, Icons, Segmented, Textarea, useToast } from "@/components/ui";
import { CredentialFields, useClinicianCredentials } from "@/features/doctor/credential-fields";
import type { Me } from "@/features/doctor/use-doctor";

/** Record the consultation, then release the visit summary. Both actions are attributed to
 * a verified HMS login, so each carries the clinician's credentials. */
export function ConsultationForm({ c, me, onDone }: { c: CaseDetail; me: Me; onDone: () => Promise<void> }) {
  const hasNote = c.consultation_notes.length > 0;
  const [mode, setMode] = useState<"in_person" | "virtual">("in_person");
  const [notes, setNotes] = useState("");
  const [prescription, setPrescription] = useState("");
  const [followUp, setFollowUp] = useState("");
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
        consultation_mode: mode, notes: notes.trim(),
        prescription: prescription.trim() || undefined, follow_up_instructions: followUp.trim() || undefined,
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
          <div className="rounded-md border border-line bg-sunken/60 px-3.5 py-3 text-sm">
            <p className="text-xs text-fg-muted">{n.consultation_mode === "virtual" ? "Virtual" : "In-person"} consultation · {n.doctor_name ?? n.doctor_id}</p>
            <p className="mt-1 whitespace-pre-line">{n.notes}</p>
            {n.prescription ? <p className="mt-2"><span className="font-medium">Prescription:</span> {n.prescription}</p> : null}
            {n.follow_up_instructions ? <p className="mt-1"><span className="font-medium">Follow-up:</span> {n.follow_up_instructions}</p> : null}
          </div>
          <CredentialFields idPrefix="finalizer" value={credentials} onChange={setCredentials}
          signingInAs={me.username ? `${me.name} (${me.username})` : null}
            hint="Verified against the hospital system to record who released this summary" />
          {error ? <Alert tone="danger">{error}</Alert> : null}
          <div className="flex justify-end">
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
      <CardHeader title="Record the consultation" description="Your own words. No agent writes here; the visit summary is generated from these notes afterwards." />
      <CardBody className="space-y-4">
        <Segmented label="Consultation mode" value={mode} onChange={setMode}
          options={[{ value: "in_person", label: <span className="flex items-center gap-1.5"><Icons.mapPin size={14} /> In person</span> }, { value: "virtual", label: <span className="flex items-center gap-1.5"><Icons.video size={14} /> Virtual</span> }]} />
        <Field label="Consultation notes" required htmlFor="c-notes">
          <Textarea id="c-notes" rows={5} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Findings, assessment and plan in your own words" />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Prescription" htmlFor="c-rx" hint="Shown to the patient as a prescription">
            <Textarea id="c-rx" rows={3} value={prescription} onChange={(e) => setPrescription(e.target.value)} className="min-h-0" />
          </Field>
          <Field label="Follow-up instructions" htmlFor="c-fu" hint="Becomes the draft follow-up task">
            <Textarea id="c-fu" rows={3} value={followUp} onChange={(e) => setFollowUp(e.target.value)} className="min-h-0" />
          </Field>
        </div>
        <CredentialFields idPrefix="doctor" value={credentials} onChange={setCredentials}
          signingInAs={me.username ? `${me.name} (${me.username})` : null}
          hint="Verified against the hospital system to record who authored this note" />
        {error ? <Alert tone="danger">{error}</Alert> : null}
        <div className="flex justify-end">
          <Button loading={busy === "note"} disabled={!notes.trim() || missingCredentials} onClick={saveNote} icon={<Icons.check size={16} />}>Save consultation</Button>
        </div>
      </CardBody>
    </Card>
  );
}
