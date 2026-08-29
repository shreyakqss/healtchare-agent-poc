"use client";

import { useState } from "react";
import type { ClinicianCredentials } from "@/lib/api";
import { Field, Input } from "@/components/ui";

/** Username/password pair a clinician types for each gated action. Held in component state
 * only - never persisted - and cleared by the caller after a successful submit. */
export function useClinicianCredentials(initialUsername: string) {
  const [credentials, setCredentials] = useState<ClinicianCredentials>({ username: initialUsername, password: "" });
  const missing = !credentials.username.trim() || !credentials.password;
  const clearPassword = () => setCredentials((c) => ({ ...c, password: "" }));
  return { credentials, setCredentials, missing, clearPassword };
}

export function CredentialFields({ idPrefix, value, onChange, hint, disabled, signingInAs }: {
  idPrefix: string;
  value: ClinicianCredentials;
  onChange: (next: ClinicianCredentials) => void;
  hint: string;
  disabled?: boolean;
  /** Display name of the clinician selected on the roster, when their login is known.
   * Without it the pre-filled username is an unexplained string in a box. */
  signingInAs?: string | null;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {signingInAs ? (
        <p className="text-xs text-fg-muted sm:col-span-2">
          Signing as <span className="font-medium text-fg">{signingInAs}</span>. Enter the password for this
          hospital-system login.
        </p>
      ) : null}
      <Field label="Your HMS username" htmlFor={`${idPrefix}-username`}>
        <Input id={`${idPrefix}-username`} value={value.username} disabled={disabled} readOnly autoComplete="username" />
      </Field>
      <Field label="Your HMS password" htmlFor={`${idPrefix}-password`} hint={hint}>
        <Input id={`${idPrefix}-password`} type="password" value={value.password} disabled={disabled} autoComplete="current-password"
          onChange={(e) => onChange({ ...value, password: e.target.value })} />
      </Field>
    </div>
  );
}
