import type { Metadata } from "next";
import { requireRole } from "@/lib/auth";
import { serverApi } from "@/lib/api/server";
import { AppShell } from "@/components/layout/app-shell";
import { DoctorWorkspace } from "@/features/doctor/doctor-workspace";

export const metadata: Metadata = { title: "Doctor workspace" };

export default async function DoctorPage() {
  const user = await requireRole("clinician", "/doctor");
  const [cases, config, roster] = await Promise.all([
    serverApi.clinician.cases(),
    serverApi.clinician.config(),
    serverApi.clinician.roster(),
  ]);
  return (
    <AppShell title="Doctor workspace" subtitle={config.hospital?.name} wide user={user}>
      <DoctorWorkspace
        initialCases={cases}
        initialConfig={config}
        initialRoster={roster}
        authenticatedHmsUsername={user.hms_username}
      />
    </AppShell>
  );
}
