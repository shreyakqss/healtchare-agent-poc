import type { Metadata } from "next";
import { requireRole } from "@/lib/auth";
import { serverApi } from "@/lib/api/server";
import { AppShell } from "@/components/layout/app-shell";
import { PatientPortal } from "@/features/intake/patient-portal";

export const metadata: Metadata = { title: "Patient intake" };

const FALLBACK_GREETING =
  "Hello, I am the clinic's intake assistant. Tell me what brings you in today, in your own words.";

export default async function PatientPage() {
  const user = await requireRole("patient", "/patient");
  const [config, greeting, visits, activeIntake, linkedRecord, pastAttachments] = await Promise.all([
    serverApi.patient.config(),
    serverApi.patient.greeting().catch(() => ({ text: FALLBACK_GREETING })),
    serverApi.patient.visits(),
    serverApi.patient.activeIntake(),
    serverApi.patient.linkedRecord().catch(() => null),
    serverApi.patient.pastAttachments().catch(() => []),
  ]);
  const clinicName = config?.hospital?.name ?? "Clinic";
  // Self-registered accounts get a placeholder name/email just to satisfy Keycloak's
  // profile requirements at signup - never real patient input, so never prefill with it.
  const isPlaceholder = user.email?.endsWith("@self-register.careflow.local") ?? false;

  return (
    <AppShell title="Patient intake" subtitle={clinicName} user={user}>
      <PatientPortal
        initialRequiredFields={config?.required_intake_fields ?? []}
        initialRequiredAttachmentKinds={config?.required_attachment_kinds ?? []}
        initialApiOnline
        initialLlmConfigured={config.llm_configured}
        initialGreeting={greeting.text}
        initialVisits={visits}
        initialActiveIntake={activeIntake}
        initialPastAttachments={pastAttachments}
        prefillName={linkedRecord?.name ?? (isPlaceholder ? null : user.display_name)}
        prefillEmail={linkedRecord?.email ?? (isPlaceholder ? null : user.email)}
        linkedRecord={linkedRecord}
      />
    </AppShell>
  );
}
