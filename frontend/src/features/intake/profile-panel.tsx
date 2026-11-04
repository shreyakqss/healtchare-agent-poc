"use client";

import { useState } from "react";
import { ApiError, intakeApi } from "@/lib/api";
import type { IdentityFormRequest, LinkedPatientRecord } from "@/lib/api";
import { EmptyState, useToast } from "@/components/ui/feedback";
import { Icons } from "@/components/ui/icons";
import { IntakeForm } from "@/features/intake/intake-form";

/** The patient's own registration details, edited any time and written back to their hospital
 * record. A patient who has not registered yet has no profile: their first visit creates it. */
export function ProfilePanel({ record, disabled, onSaved }: {
  record: LinkedPatientRecord | null;
  disabled?: boolean;
  onSaved: (record: LinkedPatientRecord) => void;
}) {
  const [saving, setSaving] = useState(false);
  // Remount the form after a save so it shows exactly what the hospital record now holds.
  const [version, setVersion] = useState(0);
  const toast = useToast();

  if (!record) {
    return (
      <EmptyState
        icon={<Icons.user size={20} />}
        title="No profile yet"
        description="Your profile is created when you register for your first visit. After that you can update it here."
      />
    );
  }

  async function save(values: IdentityFormRequest) {
    setSaving(true);
    try {
      const saved = await intakeApi.saveProfile(values);
      onSaved(saved);
      setVersion((v) => v + 1);
      toast.push({ tone: "success", message: "Profile saved." });
    } catch (err) {
      toast.push({ tone: "danger", message: err instanceof ApiError ? err.message : "Could not save your profile. Please try again." });
    } finally {
      setSaving(false);
    }
  }

  return (
    <IntakeForm key={version} mode="profile" linkedRecord={record} busy={saving} disabled={disabled} onSubmit={(v) => void save(v)} />
  );
}
