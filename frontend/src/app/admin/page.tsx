import { AppShell } from "@/components/layout/app-shell";
import { hmsApi, hospitalApi, safe } from "@/lib/api";
import { AdminConsole } from "@/features/admin/admin-console";

export const metadata = { title: "Configuration" };

export default async function AdminPage() {
  const [hospitals, active, hms] = await Promise.all([
    safe(hospitalApi.list(), []),
    safe(hospitalApi.config(), null),
    safe(hmsApi.status(), null),
  ]);
  const { hospital_id, ...config } = active ?? { hospital_id: null };

  return (
    <AppShell title="Configuration" subtitle="Clinic setup" wide>
      <AdminConsole
        initialHospitals={hospitals}
        initialConfig={active ? (config as Parameters<typeof AdminConsole>[0]["initialConfig"]) : null}
        initialActiveId={hospital_id}
        initialHms={hms}
      />
    </AppShell>
  );
}