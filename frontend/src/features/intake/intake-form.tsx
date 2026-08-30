"use client";

import { useState } from "react";
import type { IdentityFormRequest, LinkedPatientRecord } from "@/lib/api";
import { Alert, Button, Card, CardBody, CardHeader, Field, Icons, Input, Select } from "@/components/ui";

interface Draft {
  name: string;
  birth_date: string;
  gender: string;
  phone: string;
  email: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  contact_preference: string;
}

const EMPTY_DRAFT: Draft = {
  name: "", birth_date: "", gender: "", phone: "", email: "", address_line1: "", address_line2: "",
  city: "", state: "", postal_code: "", country: "", contact_preference: "",
};

const REQUIRED_KEYS = ["name", "birth_date", "gender", "address_line1", "city", "state", "postal_code", "country", "contact_preference"] as const;

export function IntakeForm({ onSubmit, busy, disabled, prefillName, prefillEmail, linkedRecord }: {
  onSubmit: (values: IdentityFormRequest) => void;
  busy: boolean;
  disabled?: boolean;
  // From the signed-in Keycloak account, so the patient doesn't retype what's already known.
  // Used only when there is no linkedRecord (a brand-new account, not yet tied to an OpenEMR patient).
  prefillName?: string | null;
  prefillEmail?: string | null;
  // Full prefill when this account is linked to an existing OpenEMR patient (Keycloak
  // `hms_patient_id`) - submitting still updates that same record, never creates a second one.
  linkedRecord?: LinkedPatientRecord | null;
}) {
  const [draft, setDraft] = useState<Draft>(() =>
    linkedRecord
      ? {
          name: linkedRecord.name,
          birth_date: linkedRecord.birth_date ?? "",
          gender: linkedRecord.gender.toLowerCase(),
          phone: linkedRecord.phone ?? "",
          email: linkedRecord.email ?? "",
          address_line1: linkedRecord.address_line1 ?? "",
          address_line2: linkedRecord.address_line2 ?? "",
          city: linkedRecord.city ?? "",
          state: linkedRecord.state ?? "",
          postal_code: linkedRecord.postal_code ?? "",
          country: linkedRecord.country ?? "",
          contact_preference: linkedRecord.contact_preference ?? "",
        }
      : {
          ...EMPTY_DRAFT,
          name: prefillName ?? "",
          email: prefillEmail ?? "",
          contact_preference: prefillEmail ? "email" : "",
        },
  );
  const [consented, setConsented] = useState(false);
  const [touched, setTouched] = useState(false);

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  const requiredMissing = REQUIRED_KEYS.filter((k) => !draft[k].trim());
  // Which contact field is required depends on the chosen contact method - the other one is
  // hidden and not collected, so it can't be what's missing.
  const contactMissing =
    draft.contact_preference === "phone" ? !draft.phone.trim() :
    draft.contact_preference === "email" ? !draft.email.trim() : false;
  const canSubmit = requiredMissing.length === 0 && !contactMissing && consented && !busy && !disabled;

  function submit() {
    setTouched(true);
    if (!canSubmit) return;
    onSubmit({
      name: draft.name.trim(),
      birth_date: draft.birth_date,
      gender: draft.gender.trim(),
      phone: draft.phone.trim() || undefined,
      email: draft.email.trim() || undefined,
      address_line1: draft.address_line1.trim(), address_line2: draft.address_line2.trim() || undefined,
      city: draft.city.trim(), state: draft.state.trim(), postal_code: draft.postal_code.trim(), country: draft.country.trim(),
      contact_preference: draft.contact_preference.trim(),
    });
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title="Your details"
          description={
            linkedRecord
              ? "Filled in from your last visit - please confirm or update anything that's changed."
              : "We use these details to create your clinic record. Next, the assistant will ask what brings you in."
          }
        />
        <CardBody className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Full name" required htmlFor="f-name" error={touched && !draft.name.trim() ? "Required" : null}>
              <Input id="f-name" value={draft.name} onChange={(e) => set("name", e.target.value)} disabled={disabled} />
            </Field>
            <Field label="Date of birth" required htmlFor="f-birth-date" error={touched && !draft.birth_date ? "Required" : null}>
              <Input id="f-birth-date" type="date" value={draft.birth_date} onChange={(e) => set("birth_date", e.target.value)} disabled={disabled} />
            </Field>
            <Field label="Gender" required htmlFor="f-gender" error={touched && !draft.gender.trim() ? "Required" : null}>
              <Select id="f-gender" value={draft.gender} onChange={(e) => set("gender", e.target.value)} disabled={disabled}>
                <option value="">Select...</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="other">Other</option>
                <option value="prefer not to say">Prefer not to say</option>
              </Select>
            </Field>
            <Field label="Contact preference" required htmlFor="f-contact" error={touched && !draft.contact_preference.trim() ? "Required" : null}>
              <Select id="f-contact" value={draft.contact_preference} onChange={(e) => set("contact_preference", e.target.value)} disabled={disabled}>
                <option value="">Select...</option>
                <option value="phone">Phone call</option>
                <option value="email">Email</option>
              </Select>
            </Field>
            {draft.contact_preference === "phone" ? (
              <Field label="Phone" required htmlFor="f-phone" error={touched && contactMissing ? "Required" : null}>
                <Input id="f-phone" type="tel" value={draft.phone} onChange={(e) => set("phone", e.target.value)} disabled={disabled} />
              </Field>
            ) : null}
            {draft.contact_preference === "email" ? (
              <Field label="Email" required htmlFor="f-email" error={touched && contactMissing ? "Required" : null}>
                <Input id="f-email" type="email" value={draft.email} onChange={(e) => set("email", e.target.value)} disabled={disabled} />
              </Field>
            ) : null}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Address" required htmlFor="f-address" error={touched && !draft.address_line1.trim() ? "Required" : null}><Input id="f-address" value={draft.address_line1} onChange={(e) => set("address_line1", e.target.value)} disabled={disabled} /></Field>
            <Field label="Address line 2" htmlFor="f-address-2"><Input id="f-address-2" value={draft.address_line2} onChange={(e) => set("address_line2", e.target.value)} disabled={disabled} /></Field>
            <Field label="City" required htmlFor="f-city" error={touched && !draft.city.trim() ? "Required" : null}><Input id="f-city" value={draft.city} onChange={(e) => set("city", e.target.value)} disabled={disabled} /></Field>
            <Field label="State" required htmlFor="f-state" error={touched && !draft.state.trim() ? "Required" : null}><Input id="f-state" value={draft.state} onChange={(e) => set("state", e.target.value)} disabled={disabled} /></Field>
            <Field label="Postal code" required htmlFor="f-postal" error={touched && !draft.postal_code.trim() ? "Required" : null}><Input id="f-postal" value={draft.postal_code} onChange={(e) => set("postal_code", e.target.value)} disabled={disabled} /></Field>
            <Field label="Country" required htmlFor="f-country" error={touched && !draft.country.trim() ? "Required" : null}><Input id="f-country" value={draft.country} onChange={(e) => set("country", e.target.value)} disabled={disabled} /></Field>
          </div>
        </CardBody>
      </Card>

      <label className="flex cursor-pointer items-start gap-3 rounded-md border border-line bg-sunken px-3.5 py-3 text-sm leading-5 text-fg-muted">
        <input type="checkbox" checked={consented} onChange={(e) => setConsented(e.target.checked)} className="mt-0.5 h-4 w-4 shrink-0 accent-brand" disabled={disabled} />
        <span>I understand this is a demo and agree to the processing of the information I share. A clinician reviews everything before any decision is made.</span>
      </label>

      {touched && !consented ? <Alert tone="warning">Please confirm consent before continuing.</Alert> : null}

      <div className="flex justify-end">
        <Button onClick={submit} loading={busy} disabled={disabled || (touched && !canSubmit)} icon={<Icons.arrowRight size={16} />}>
          Continue
        </Button>
      </div>
    </div>
  );
}
