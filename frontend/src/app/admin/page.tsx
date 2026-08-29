import { AppShell } from "@/components/layout/app-shell";
import { requireRole } from "@/lib/auth";
import { serverApi } from "@/lib/api/server";
import { AdminConsole } from "@/features/admin/admin-console";

export const metadata = { title: "Configuration" };

export default async function AdminPage() {
  const user = await requireRole("admin", "/admin");
  const [hospitals, active, hms] = await Promise.all([
    serverApi.admin.hospitals(),
    serverApi.admin.config(),
    serverApi.admin.hms(),
  ]);
  const { hospital_id, ...config } = active ?? { hospital_id: null };

  return (
    <AppShell title="Configuration" subtitle="Clinic setup" wide user={user}>
      <AdminConsole
        initialHospitals={hospitals}
        initialConfig={active ? (config as Parameters<typeof AdminConsole>[0]["initialConfig"]) : null}
        initialActiveId={hospital_id}
        initialHms={hms}
      />
    </AppShell>
  );
}
