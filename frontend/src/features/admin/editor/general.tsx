"use client";

import { useState } from "react";
import { hospitalApi } from "@/lib/api";
import type { HospitalConfig } from "@/lib/api/types";
import { Card, CardBody, CardHeader, Field, Icons, Input, KeyValue, useToast } from "@/components/ui";
import type { ConfigEditor } from "@/features/admin/use-config-editor";

export function GeneralTab({ editor, hospitalId }: { editor: ConfigEditor; hospitalId: string }) {
  const cfg = editor.config as HospitalConfig;
  const set = (patch: Partial<HospitalConfig["hospital"]>) => editor.update((c) => ({ ...c, hospital: { ...c.hospital, ...patch } }));
  const toast = useToast();
  const [hasLetterhead, setHasLetterhead] = useState(true);
  const [cacheBust, setCacheBust] = useState(0);
  const [uploading, setUploading] = useState(false);

  async function handleLetterhead(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      await hospitalApi.uploadLetterhead(hospitalId, file);
      setHasLetterhead(true);
      setCacheBust((n) => n + 1);
      toast.push({ tone: "success", message: "Letterhead uploaded" });
    } catch (err) {
      toast.push({ tone: "danger", message: err instanceof Error ? err.message : "Could not upload the letterhead." });
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader
          title="Clinic details"
          description="The clinic's name and address are read from the hospital system's own facility record. These are the fallback for when it has none."
        />
        <CardBody className="grid gap-4 sm:grid-cols-2">
          <Field label="Display name" htmlFor="h-name" required hint="Overridden by the hospital system's facility name when it has one.">
            <Input id="h-name" value={cfg.hospital?.name ?? ""} onChange={(e) => set({ name: e.target.value })} />
          </Field>
          <Field label="Timezone" htmlFor="h-tz" hint="IANA name, e.g. Asia/Kolkata">
            <Input id="h-tz" value={cfg.hospital?.timezone ?? ""} onChange={(e) => set({ timezone: e.target.value })} />
          </Field>
          <Field label="Identifier" htmlFor="h-id" hint="Fixed at creation; it is the configuration file name.">
            <Input id="h-id" value={hospitalId} readOnly aria-readonly className="bg-sunken font-mono" />
          </Field>
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="At a glance" />
        <CardBody>
          <KeyValue columns={2} items={[
            { label: "Departments", value: <span className="tabular">{cfg.departments?.length ?? 0}</span> },
            { label: "Static doctor overrides", value: <span className="tabular">{cfg.doctors?.length ?? 0}</span> },
            { label: "Appointment types", value: <span className="tabular">{cfg.appointment_types?.length ?? 0}</span> },
            { label: "Triage rules", value: <span className="tabular">{cfg.triage_rules?.rules?.length ?? 0}</span> },
            { label: "Rule version", value: <span className="font-mono text-xs">{cfg.triage_rules?.version ?? "–"}</span> },
            { label: "Intake fields", value: <span className="tabular">{cfg.required_intake_fields?.length ?? 0}</span> },
          ]} />
        </CardBody>
      </Card>
      <Card className="lg:col-span-3">
        <CardHeader title="Letterhead" description="Used as the header of the doctor's report to the patient, in place of the plain name/address block, once uploaded." />
        <CardBody className="space-y-3">
          {hasLetterhead ? (
            // eslint-disable-next-line @next/next/no-img-element -- admin-uploaded clinic asset, not a static import
            <img
              src={`${hospitalApi.letterheadUrl(hospitalId)}?v=${cacheBust}`}
              alt="Clinic letterhead"
              className="max-h-32 rounded-md border border-line bg-sunken object-contain"
              onError={() => setHasLetterhead(false)}
            />
          ) : (
            <p className="text-sm text-fg-subtle">No letterhead uploaded yet.</p>
          )}
          <label className="inline-flex w-fit cursor-pointer items-center gap-2 rounded-md border border-line px-3 py-2 text-sm font-medium hover:bg-sunken">
            <Icons.upload size={16} />
            {uploading ? "Uploading…" : "Upload letterhead"}
            <input type="file" accept="image/png,image/jpeg" className="hidden" onChange={handleLetterhead} disabled={uploading} />
          </label>
        </CardBody>
      </Card>
    </div>
  );
}