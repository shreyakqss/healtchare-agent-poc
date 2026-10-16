import type { Metadata } from "next";
import { requireRole } from "@/lib/auth";
import { serverApi } from "@/lib/api/server";
import { AppShell } from "@/components/layout/app-shell";
import { DoctorWorkspace } from "@/features/doctor/doctor-workspace";

export const metadata: Metadata = { title: "Doctor workspace" };

export default async function DoctorPage() {
  const user = await requireRole("clinician", "/doctor");
  const [cases, config, roster, hours] = await Promise.all([
    serverApi.clinician.cases(),
    serverApi.clinician.config(),
    serverApi.clinician.roster(),
    serverApi.clinician.myHours().catch(() => []), // display-only: no hours box if it cannot load
  ]);
  return (
    <AppShell title="Doctor workspace" subtitle={config.hospital?.name} wide user={user}>
      <DoctorWorkspace
        initialCases={cases}
        initialConfig={config}
        initialRoster={roster}
        initialHours={hours}
        authenticatedHmsUsername={user.hms_username}
      />
    </AppShell>
  );
}
