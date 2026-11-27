import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Alert } from "@/components/ui";
import { requireRole } from "@/lib/auth";
import { ApiError } from "@/lib/api/client";
import { serverApi } from "@/lib/api/server";
import { DoctorsConsole } from "@/features/admin/doctors/doctors-console";
import type { AdminDoctors } from "@/lib/api/types";

export const metadata = { title: "Doctors" };

export default async function AdminDoctorsPage() {
  const user = await requireRole("admin", "/admin/doctors");
  let initial: AdminDoctors | null = null;
  let error: string | null = null;
  try {
    initial = await serverApi.admin.doctors();
  } catch (e) {
    // 403: admin login not linked to a hospital; 422: hospital not linked to a facility; 503: a system is down.
    error = e instanceof ApiError ? e.message : "Could not load the doctors.";
  }

  return (
    <AppShell title="Doctors" subtitle="Clinic setup" wide user={user}>
      {initial ? <DoctorsConsole initial={initial} /> : (
        <>
          <PageHeader title="Doctors" description="Add doctors to your hospital and keep their consulting hours published." />
          <Alert tone="danger" title="Doctors are unavailable">{error}</Alert>
        </>
      )}
    </AppShell>
  );
}
