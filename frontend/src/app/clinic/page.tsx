import type { Metadata } from "next";
import { AppShell } from "@/components/layout/app-shell";
import { casesApi, healthApi, hmsApi, hospitalApi, safe } from "@/lib/api";
import { ClinicDesk } from "@/features/clinic/clinic-desk";

export const metadata: Metadata = { title: "Clinic desk" };

export default async function ClinicPage() {
  const [cases, overview, config, hmsStatus, requests, health] = await Promise.all([
    safe(casesApi.list(), null),
    safe(casesApi.overview(), null),
    safe(hospitalApi.config(), null),
    safe(hmsApi.status(), null),
    safe(hmsApi.requests(), []),
    safe(healthApi.get(), null),
  ]);

  return (
    <AppShell title="Clinic desk" subtitle={config?.hospital?.name ?? "Clinic"} wide>
      <ClinicDesk
        initialCases={cases}
        initialOverview={overview}
        initialConfig={config}
        initialHmsStatus={hmsStatus}
        initialRequests={requests}
        initialHealth={health}
      />
    </AppShell>
  );
}