"use client";

import { useState } from "react";
import { ApiError, casesApi, hospitalApi, type CaseDetail, type HospitalIdentity } from "@/lib/api";
import { Alert, Button, Card, CardBody, CardHeader, Dialog, Field, Icons, Textarea, useToast } from "@/components/ui";
import { briefingOf } from "@/features/doctor/briefing";
import { CredentialFields, useClinicianCredentials } from "@/features/doctor/credential-fields";
import type { Me } from "@/features/doctor/use-doctor";

const EDITABLE: Array<{ key: keyof ReturnType<typeof briefingOf>; label: string }> = [
  { key: "chief_complaint", label: "Chief complaint" },
  { key: "reported_symptoms", label: "Reported symptoms" },
  { key: "relevant_history", label: "Relevant history" },
  { key: "medications", label: "Medications" },
  { key: "allergies", label: "Allergies" },
];

function asText(v: unknown): string {
  return Array.isArray(v) ? v.join("\n") : typeof v === "string" ? v : "";
}

export function ReviewForm({ c, me, onDone, hospital }: { c: CaseDetail; me: Me; onDone: () => Promise<void>; hospital: HospitalIdentity | null }) {
  const [open, setOpen] = useState(false);
  const [returning, setReturning] = useState(false);
  const b = briefingOf(c);
  const initial = Object.fromEntries(EDITABLE.map((e) => [e.key, asText(b[e.key])])) as Record<string, string>;
  const [values, setValues] = useState(initial);
  const [reason, setReason] = useState("");
  const { credentials, setCredentials, missing: missingCredentials, clearPassword } = useClinicianCredentials(me.username ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const edits = Object.fromEntries(Object.entries(values).filter(([k, v]) => v.trim() !== initial[k].trim()));

  function reset() {
    setValues(initial);
    setReason("");
    setReturning(false);
    setError(null);
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await casesApi.review(c.case_id, {
        decision: returning ? "reject" : Object.keys(edits).length ? "edit" : "approve",
        reviewer_username: credentials.username.trim(), reviewer_password: credentials.password,
        edits: returning ? {} : edits, comment: reason.trim() || undefined,
      });
      toast.push({ tone: "success", message: returning ? "Visit returned" : "Visit recorded" });
      clearPassword();
      setOpen(false);
      reset();
      await onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not record the review. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Card className="border-brand-ring/40">
        <CardHeader title="Your review" description="Write it up here, then release it. Edits are stored beside the patient's statements, never over them." />
        <CardBody>
          <Button icon={<Icons.edit size={16} />} onClick={() => setOpen(true)}>Write review</Button>
        </CardBody>
      </Card>

      <Dialog open={open} onClose={() => { setOpen(false); reset(); }} size="xl" title="Review this visit" description="Left is what you change; right is the record as it stands.">
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              {EDITABLE.map((e) => (
                <Field key={e.key} label={e.label} htmlFor={`edit-${e.key}`} hint={e.key === "chief_complaint" ? undefined : "One item per line"}>
                  <Textarea id={`edit-${e.key}`} rows={e.key === "chief_complaint" ? 2 : 3} value={values[e.key]}
                    onChange={(ev) => setValues((v) => ({ ...v, [e.key]: ev.target.value }))} className="min-h-0" />
                </Field>
              ))}
            </div>

            <Field label={returning ? "Reason this is being returned" : "Note"} required={returning} htmlFor="review-comment">
              <Textarea id="review-comment" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} className="min-h-0"
                placeholder={returning ? "What needs to change before this can proceed" : "Optional note for the record"} />
            </Field>

            {!returning ? (
              <button type="button" onClick={() => setReturning(true)} className="text-xs text-fg-subtle underline decoration-dotted hover:text-fg-muted">
                This visit needs to go back to intake instead
              </button>
            ) : (
              <button type="button" onClick={() => setReturning(false)} className="text-xs text-fg-subtle underline decoration-dotted hover:text-fg-muted">
                Cancel, write the record instead
              </button>
            )}

            {error ? <Alert tone="danger">{error}</Alert> : null}
          </div>

          <RecordDocument patientName={c.demographics.name} briefing={b} edits={edits} hospital={hospital} />
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
          <CredentialFields idPrefix="reviewer" value={credentials} onChange={setCredentials}
            signingInAs={me.username ? `${me.name} (${me.username})` : null}
            hint="Verified against the hospital system" />
          <Button
            variant={returning ? "danger" : "primary"} loading={busy}
            disabled={(returning && !reason.trim()) || missingCredentials} onClick={submit}
            icon={returning ? <Icons.x size={16} /> : <Icons.check size={16} />}
          >
            {returning ? "Return visit" : "Submit review"}
          </Button>
        </div>
      </Dialog>
    </>
  );
}

/** Live, letterhead-styled preview of the record as it stands - the clinic's own uploaded
 * letterhead when set (see admin "Letterhead" panel), the facility name/address otherwise. */
function RecordDocument({ patientName, briefing, edits, hospital }: {
  patientName: string; briefing: ReturnType<typeof briefingOf>; edits: Record<string, string>; hospital: HospitalIdentity | null;
}) {
  const addressLine = hospital?.address
    ? [hospital.address.line1, hospital.address.city, hospital.address.state, hospital.address.postal_code].filter(Boolean).join(", ")
    : null;
  const contactLine = hospital ? [hospital.phone, hospital.email].filter(Boolean).join(" · ") : null;
  const rows = EDITABLE.map((e) => ({ label: e.label, value: e.key in edits ? edits[e.key] : asText(briefing[e.key]) }));

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
          <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">Visit record</p>
        )}
      </div>
      <div className="max-h-[26rem] space-y-4 overflow-y-auto px-5 py-4">
        <dl className="grid grid-cols-2 gap-2 text-xs text-fg-muted">
          <div><dt className="text-fg-subtle">Patient</dt><dd className="font-medium text-fg">{patientName || "Unnamed patient"}</dd></div>
          <div><dt className="text-fg-subtle">Date</dt><dd className="font-medium text-fg" suppressHydrationWarning>{new Date().toLocaleDateString()}</dd></div>
        </dl>
        <hr className="border-line" />
        <dl className="space-y-3">
          {rows.map((r) => (
            <div key={r.label}>
              <dt className="text-xs font-medium text-fg-muted">{r.label}</dt>
              <dd className="mt-0.5 whitespace-pre-wrap text-[15px] leading-6 text-fg">{r.value || "–"}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
