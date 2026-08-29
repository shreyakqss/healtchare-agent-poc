"use client";

import { useState } from "react";
import { ApiError, casesApi, type CaseDetail, type CaseListItem, type HospitalConfig, type Roster } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Alert, Avatar, Button, EmptyState, Icons, useToast } from "@/components/ui";
import { CasePanel, CasePanelSkeleton } from "@/features/doctor/case-panel";
import { resolveMe } from "@/features/doctor/use-doctor";
import { Worklist, bucketOf, isMine } from "@/features/doctor/worklist";

export function DoctorWorkspace({ initialCases, initialConfig, initialRoster, authenticatedHmsUsername }: {
  initialCases: CaseListItem[]; initialConfig: HospitalConfig | null; initialRoster: Roster | null;
  authenticatedHmsUsername: string | null;
}) {
  // The roster endpoint merges live hospital-system practitioners over the clinic config; if
  // it is unavailable, fall back to whatever doctors the config itself declares (usually none).
  const roster: Roster = initialRoster ?? {
    source: "config",
    doctors: (initialConfig?.doctors ?? []).map((d) => ({ ...d, specialty: null, working_days: d.working_days ?? [], username: d.username ?? null })),
  };
  const me = resolveMe(authenticatedHmsUsername, roster.doctors, initialConfig?.departments ?? []);
  const [cases, setCases] = useState(initialCases);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const toast = useToast();

  if (!initialConfig) {
    return <Alert tone="danger" title="Clinic configuration unavailable">The API did not return a hospital configuration. Start the backend and reload.</Alert>;
  }
  if (!me) {
    return (
      <Alert tone="danger" title="Hospital identity is not linked">
        Ask an administrator to set your Keycloak <code>hms_username</code> attribute to your OpenEMR username.
      </Alert>
    );
  }

  async function refreshList() {
    setRefreshing(true);
    try {
      setCases(await casesApi.list());
      setNow(Date.now());
    } catch {
      toast.push({ tone: "danger", message: "Could not refresh the worklist" });
    } finally {
      setRefreshing(false);
    }
  }

  async function select(id: string) {
    setSelectedId(id);
    setLoading(true);
    setError(null);
    try {
      setDetail(await casesApi.get(id));
    } catch (e) {
      setDetail(null);
      setError(e instanceof ApiError ? e.message : "Could not load the case.");
    } finally {
      setLoading(false);
    }
  }

  async function onChanged() {
    if (selectedId) await select(selectedId);
    await refreshList();
  }

  const mine = cases.filter((c) => isMine(c, me));
  const counts = { review: 0, consult: 0, completed: 0, other: 0 };
  for (const c of mine) counts[bucketOf(c)] += 1;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Avatar name={me.name} />
        <div className="min-w-0">
          <p className="text-sm font-semibold leading-5">{me.name}</p>
          <p className="text-xs text-fg-muted">{me.department_name}</p>
        </div>
        <p className="ml-auto hidden text-xs text-fg-subtle sm:block">Reviews, notes and releases are verified against your hospital-system login.</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[380px_minmax(0,1fr)]">
        <div className={cn("lg:sticky lg:top-20 lg:h-[calc(100dvh-7rem)]", selectedId && "hidden lg:block")}>
          <Worklist cases={cases} me={me} selectedId={selectedId} onSelect={select} onRefresh={refreshList} refreshing={refreshing} now={now} />
        </div>

        <div className={cn("min-w-0", !selectedId && "hidden lg:block")}>
          {loading ? <CasePanelSkeleton /> : null}
          {!loading && error ? (
            <Alert tone="danger" title="Could not load this case">
              {error} <Button variant="ghost" size="sm" className="ml-2" onClick={() => selectedId && select(selectedId)}>Retry</Button>
            </Alert>
          ) : null}
          {!loading && !error && detail ? (
            <CasePanel c={detail} me={me} onBack={() => { setSelectedId(null); setDetail(null); }} onChanged={onChanged} />
          ) : null}
          {!loading && !error && !detail ? (
            <div className="rounded-lg border border-dashed border-line-strong">
              <EmptyState
                icon={<Icons.stethoscope size={20} />}
                title="Select a case"
                description={`${counts.review} awaiting review · ${counts.consult} ready to consult · ${counts.completed} completed`}
              />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
