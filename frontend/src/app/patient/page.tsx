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
  const [config, greeting, visits, activeIntake] = await Promise.all([
    serverApi.patient.config(),
    serverApi.patient.greeting().catch(() => ({ text: FALLBACK_GREETING })),
    serverApi.patient.visits(),
    serverApi.patient.activeIntake(),
  ]);
  const clinicName = config?.hospital?.name ?? "Clinic";

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
      />
    </AppShell>
  );
}
