"use client";

import { useState } from "react";
import type { ClinicianCredentials } from "@/lib/api";
import { Input } from "@/components/ui";

/** Username/password pair a clinician types for each gated action. Held in component state
 * only - never persisted - and cleared by the caller after a successful submit. */
export function useClinicianCredentials(initialUsername: string) {
  const [credentials, setCredentials] = useState<ClinicianCredentials>({ username: initialUsername, password: "" });
  const missing = !credentials.username.trim() || !credentials.password;
  const clearPassword = () => setCredentials((c) => ({ ...c, password: "" }));
  return { credentials, setCredentials, missing, clearPassword };
}

/** One line: the clinician's already-known hospital-system login (read from their Keycloak
 * session, never typed) plus the single password field that actually authorizes the action -
 * verified live against the hospital system itself, not just this app's session. No separate
 * username box or paragraph; `value.username` still travels with the submit unchanged. */
export function CredentialFields({ idPrefix, value, onChange, hint, disabled, signingInAs }: {
  idPrefix: string;
  value: ClinicianCredentials;
  onChange: (next: ClinicianCredentials) => void;
  hint: string;
  disabled?: boolean;
  signingInAs?: string | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label htmlFor={`${idPrefix}-password`} className="shrink-0 text-sm text-fg-muted">
        {signingInAs ? <>Confirm as <span className="font-medium text-fg">{signingInAs}</span></> : "Password"}
      </label>
      <Input
        id={`${idPrefix}-password`} type="password" value={value.password} disabled={disabled}
        autoComplete="current-password" placeholder={hint} title={hint}
        className="w-48"
        onChange={(e) => onChange({ ...value, password: e.target.value })}
      />
    </div>
  );
}
