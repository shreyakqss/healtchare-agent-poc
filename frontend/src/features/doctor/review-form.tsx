"use client";

import { useState } from "react";
import { ApiError, casesApi, type CaseDetail, type ReviewDecision } from "@/lib/api";
import { Alert, Button, Card, CardBody, CardHeader, Field, Icons, Segmented, Textarea, useToast } from "@/components/ui";
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

export function ReviewForm({ c, me, onDone }: { c: CaseDetail; me: Me; onDone: () => Promise<void> }) {
  const b = briefingOf(c);
  const initial = Object.fromEntries(EDITABLE.map((e) => [e.key, asText(b[e.key])])) as Record<string, string>;
  const [decision, setDecision] = useState<ReviewDecision>("approve");
  const [values, setValues] = useState(initial);
  const [comment, setComment] = useState("");
  const { credentials, setCredentials, missing: missingCredentials, clearPassword } = useClinicianCredentials(me.username ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const edits = Object.fromEntries(Object.entries(values).filter(([k, v]) => v.trim() !== initial[k].trim()));
  const rejectMissingComment = decision === "reject" && !comment.trim();
  const editNothingChanged = decision === "edit" && Object.keys(edits).length === 0;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await casesApi.review(c.case_id, {
        decision, reviewer_username: credentials.username.trim(), reviewer_password: credentials.password,
        edits: decision === "edit" ? edits : {}, comment: comment.trim() || undefined,
      });
      toast.push({ tone: "success", message: decision === "reject" ? "Case rejected" : "Case approved" });
      clearPassword();
      await onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not record the review. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="border-brand-ring/40">
      <CardHeader title="Your review" description="Nothing reaches the patient until you approve. Edits are stored beside the patient's statements, never over them." />
      <CardBody className="space-y-4">
        <Segmented
          label="Decision" value={decision} onChange={setDecision}
          options={[{ value: "approve", label: "Approve" }, { value: "edit", label: "Approve with edits" }, { value: "reject", label: "Reject" }]}
        />

        {decision === "edit" ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {EDITABLE.map((e) => (
              <Field key={e.key} label={e.label} htmlFor={`edit-${e.key}`} hint={e.key === "chief_complaint" ? undefined : "One item per line"}>
                <Textarea id={`edit-${e.key}`} rows={e.key === "chief_complaint" ? 2 : 3} value={values[e.key]}
                  onChange={(ev) => setValues((v) => ({ ...v, [e.key]: ev.target.value }))} className="min-h-0" />
              </Field>
            ))}
          </div>
        ) : null}

        <Field label={decision === "reject" ? "Reason for rejection" : "Comment"} required={decision === "reject"} htmlFor="review-comment">
          <Textarea id="review-comment" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} className="min-h-0"
            placeholder={decision === "reject" ? "Why this case is being returned" : "Optional note for the record"} />
        </Field>

        {editNothingChanged ? <Alert tone="info">No field differs from the briefing yet. Change something, or switch to Approve.</Alert> : null}

        <CredentialFields idPrefix="reviewer" value={credentials} onChange={setCredentials}
          signingInAs={me.username ? `${me.name} (${me.username})` : null}
          hint="Verified against the hospital system to record who approved this case" />

        {error ? <Alert tone="danger">{error}</Alert> : null}

        <div className="flex justify-end gap-2">
          <Button
            variant={decision === "reject" ? "danger" : "primary"} loading={busy}
            disabled={rejectMissingComment || editNothingChanged || missingCredentials} onClick={submit}
            icon={decision === "reject" ? <Icons.x size={16} /> : <Icons.check size={16} />}
          >
            {decision === "approve" ? "Approve case" : decision === "edit" ? "Approve with edits" : "Reject case"}
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}
