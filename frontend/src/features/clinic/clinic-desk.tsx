"use client";

import { useState } from "react";
import { Alert, Button, Card, Icons, Tabs, useToast } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { casesApi, hmsApi } from "@/lib/api";
import type { AppointmentRequestResult, CaseListItem, ClinicOverview, Health, HMSStatus, HospitalConfig } from "@/lib/api/types";
import { EMPTY_FILTERS, filterQueue, sortQueue, type QueueFilters as Filters } from "@/features/clinic/derive";
import { StatsRow } from "@/features/clinic/stats-row";
import { QueueFilters } from "@/features/clinic/queue-filters";
import { QueueTable } from "@/features/clinic/queue-table";
import { PatientsDirectory } from "@/features/clinic/patients-directory";
import { DoctorsPanel } from "@/features/clinic/doctors-panel";
import { HmsPanel } from "@/features/clinic/hms-panel";

type Tab = "queue" | "patients" | "doctors" | "hms";

export function ClinicDesk({ initialCases, initialOverview, initialConfig, initialHmsStatus, initialRequests, initialHealth }: {
  initialCases: CaseListItem[] | null;
  initialOverview: ClinicOverview | null;
  initialConfig: (HospitalConfig & { hospital_id: string }) | null;
  initialHmsStatus: HMSStatus | null;
  initialRequests: AppointmentRequestResult[];
  initialHealth: Health | null;
}) {
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("queue");
  const [cases, setCases] = useState<CaseListItem[]>(initialCases ?? []);
  const [overview, setOverview] = useState(initialOverview);
  const [hms, setHms] = useState(initialHmsStatus);
  const [requests, setRequests] = useState(initialRequests);
  const [apiDown, setApiDown] = useState(initialCases === null);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [now, setNow] = useState(() => Date.now());
  const [refreshing, setRefreshing] = useState(false);

  async function refresh() {
    setRefreshing(true);
    try {
      const [list, ov, st, rq] = await Promise.all([casesApi.list(), casesApi.overview(), hmsApi.status(), hmsApi.requests()]);
      setCases(list); setOverview(ov); setHms(st); setRequests(rq); setApiDown(false); setNow(Date.now());
    } catch (e) {
      setApiDown(true);
      toast.push({ tone: "danger", message: e instanceof Error ? e.message : "Could not refresh" });
    } finally {
      setRefreshing(false);
    }
  }

  const visible = sortQueue(filterQueue(cases, filters));
  const awaiting = cases.filter((c) => c.status === "NEEDS_REVIEW").length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Clinic desk"
        description="Live queue, routing and hospital system activity. Priorities come from the clinic's approved rules; every AI output waits for clinician review."
        actions={<Button variant="secondary" onClick={refresh} loading={refreshing} icon={<Icons.refresh size={16} />}>Refresh</Button>}
      />

      {apiDown ? <Alert tone="danger" title="The API is not reachable">Start the backend (<code className="font-mono">uvicorn app.main:app --reload</code>) and refresh.</Alert> : null}

      <StatsRow cases={cases} overview={overview} health={initialHealth} hms={hms} hospitalId={initialConfig?.hospital_id ?? null} />

      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "queue", label: "Queue", count: cases.length },
          { id: "patients", label: "Patients" },
          { id: "doctors", label: "Doctors", count: initialConfig?.doctors.length },
          { id: "hms", label: "HMS", count: requests.length },
        ]}
      />

      {tab === "queue" ? (
        <Card>
          <div className="border-b border-line px-4 py-3">
            <QueueFilters value={filters} onChange={setFilters} departments={initialConfig?.departments ?? []} />
            <p className="mt-2 text-xs text-fg-subtle">
              Showing <span className="tabular text-fg-muted">{visible.length}</span> of <span className="tabular text-fg-muted">{cases.length}</span> · awaiting review first, then by priority
              {awaiting ? <> · <span className="text-warning">{awaiting} awaiting review</span></> : null}
            </p>
          </div>
          <QueueTable rows={visible} total={cases.length} now={now} />
        </Card>
      ) : null}
      {tab === "patients" ? <PatientsDirectory cases={cases} /> : null}
      {tab === "doctors" ? <DoctorsPanel cases={cases} config={initialConfig} /> : null}
      {tab === "hms" ? <HmsPanel status={hms} requests={requests} overview={overview} config={initialConfig} /> : null}
    </div>
  );
}