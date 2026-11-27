import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Alert } from "@/components/ui";
import { requireRole } from "@/lib/auth";
import { ApiError } from "@/lib/api/client";
import { serverApi } from "@/lib/api/server";
import { PatientsDirectory } from "@/features/admin/patients/patients-directory";
import type { AdminPatientItem } from "@/lib/api/types";

export const metadata = { title: "Patients" };

export default async function AdminPatientsPage() {
  const user = await requireRole("admin", "/admin/patients");
  let patients: AdminPatientItem[] | null = null;
  let error: string | null = null;
  try {
    patients = await serverApi.admin.patients();
  } catch (e) {
    error = e instanceof ApiError ? e.message : "Could not load the patients.";
  }

  return (
    <AppShell title="Patients" subtitle="Clinic directory" wide user={user}>
      {patients ? <PatientsDirectory patients={patients} /> : (
        <>
          <PageHeader title="Patients" description="Everyone registered at your clinic." />
          <Alert tone="danger" title="Patients are unavailable">{error}</Alert>
        </>
      )}
    </AppShell>
  );
}
