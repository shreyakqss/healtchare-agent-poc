import type { Metadata } from "next";
import { healthApi, hospitalApi, intakeApi, safe } from "@/lib/api";
import { AppShell } from "@/components/layout/app-shell";
import { PatientPortal } from "@/features/intake/patient-portal";

export const metadata: Metadata = { title: "Patient intake" };

const DEFAULT_GREETING =
  "Hello, I am the clinic's intake assistant. Tell me what brings you in today, in your own words.";

export default async function PatientPage() {
  const [greeting, config, health] = await Promise.all([
    safe(intakeApi.greeting(), null),
    safe(hospitalApi.config(), null),
    safe(healthApi.get(), null),
  ]);
  const clinicName = config?.hospital?.name ?? "Clinic";

  return (
    <AppShell title="Patient intake" subtitle={clinicName}>
      <PatientPortal
        initialGreeting={greeting?.text ?? DEFAULT_GREETING}
        initialRequiredFields={config?.required_intake_fields ?? []}
        initialClinicName={clinicName}
        initialApiOnline={health !== null}
        initialLlmConfigured={health?.llm.configured ?? false}
      />
    </AppShell>
  );
}