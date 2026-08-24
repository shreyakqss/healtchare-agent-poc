import type { Metadata } from "next";
import { casesApi, hospitalApi, safe } from "@/lib/api";
import { AppShell } from "@/components/layout/app-shell";
import { DoctorWorkspace } from "@/features/doctor/doctor-workspace";

export const metadata: Metadata = { title: "Doctor workspace" };

export default async function DoctorPage() {
  const [cases, config] = await Promise.all([safe(casesApi.list(), []), safe(hospitalApi.config(), null)]);
  return (
    <AppShell title="Doctor workspace" subtitle={config?.hospital?.name} wide>
      <DoctorWorkspace initialCases={cases} initialConfig={config} />
    </AppShell>
  );
}