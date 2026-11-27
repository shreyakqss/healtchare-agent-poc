import type { Metadata } from "next";
import { requireRole } from "@/lib/auth";
import { serverApi } from "@/lib/api/server";
import { AppShell } from "@/components/layout/app-shell";
import { DoctorWorkspace } from "@/features/doctor/doctor-workspace";

export const metadata: Metadata = { title: "Doctor workspace" };

export default async function DoctorPage() {
  const user = await requireRole("clinician", "/doctor");
  const [cases, past, config, roster, hours] = await Promise.all([
    serverApi.clinician.cases(),
    serverApi.clinician.pastPatients().catch(() => []), // its tab just shows empty if it cannot load
    serverApi.clinician.config(),
    serverApi.clinician.roster(),
    serverApi.clinician.myHours().catch(() => []), // display-only: no hours box if it cannot load
  ]);
  // One "now" for the server and client render, so Today/Upcoming split the same way on both.
  const now = new Date().toISOString();
  return (
    <AppShell title="Doctor workspace" subtitle={config.hospital?.name} wide user={user}>
      <DoctorWorkspace
        initialCases={cases}
        initialPast={past}
        now={now}
        initialConfig={config}
        initialRoster={roster}
        initialHours={hours}
        authenticatedHmsUsername={user.hms_username}
      />
    </AppShell>
  );
}
