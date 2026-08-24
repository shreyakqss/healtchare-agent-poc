"use client";

import { useState } from "react";
import { ApiError, hospitalApi } from "@/lib/api";
import type { HMSStatus, HospitalConfig, HospitalSummary } from "@/lib/api/types";
import { Alert, Button, EmptyState, Icons, Skeleton, Tabs, useToast } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { HospitalsRail } from "@/features/admin/hospitals-rail";
import { useConfigEditor } from "@/features/admin/use-config-editor";
import { validateConfig, type ValidationIssue } from "@/features/admin/validate";
import { GeneralTab } from "@/features/admin/editor/general";
import { DepartmentsTab } from "@/features/admin/editor/departments";
import { AppointmentsTab } from "@/features/admin/editor/appointments";
import { RoutingTab } from "@/features/admin/editor/routing";
import { TriageRulesTab } from "@/features/admin/editor/triage-rules";
import { IntakeFieldsTab } from "@/features/admin/editor/intake-fields";
import { AdvancedYamlTab } from "@/features/admin/editor/advanced-yaml";

type TabId = "general" | "departments" | "appointments" | "routing" | "rules" | "fields" | "advanced";
const TABS: Array<{ id: TabId; label: string }> = [
  { id: "general", label: "General" },
  { id: "departments", label: "Departments & doctors" },
  { id: "appointments", label: "Appointments" },
  { id: "routing", label: "Routing" },
  { id: "rules", label: "Triage rules" },
  { id: "fields", label: "Intake fields" },
  { id: "advanced", label: "Advanced" },
];

export function AdminConsole({ initialHospitals, initialConfig, initialActiveId, initialHms }: {
  initialHospitals: HospitalSummary[]; initialConfig: HospitalConfig | null; initialActiveId: string | null; initialHms: HMSStatus | null;
}) {
  const [hospitals, setHospitals] = useState(initialHospitals);
  const [selectedId, setSelectedId] = useState<string | null>(initialActiveId);
  const [tab, setTab] = useState<TabId>("general");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const editor = useConfigEditor(initialConfig);
  const toast = useToast();

  const msg = (e: unknown) => (e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Something went wrong.");

  async function refreshList() {
    setHospitals(await hospitalApi.list());
  }
  async function select(id: string) {
    if (editor.dirty && !confirm("Discard unsaved changes?")) return;
    setSelectedId(id); setLoading(true); setServerError(null); setIssues([]);
    try { editor.load(await hospitalApi.getJson(id)); }
    catch (e) { toast.push({ tone: "danger", message: msg(e) }); editor.load(null); }
    finally { setLoading(false); }
  }
  async function activate(id: string) {
    setBusy(true);
    try { await hospitalApi.activate(id); await refreshList(); toast.push({ tone: "success", message: "Clinic activated and triage rules synced." }); }
    catch (e) { toast.push({ tone: "danger", message: msg(e) }); }
    finally { setBusy(false); }
  }
  async function create(id: string) {
    setBusy(true);
    try { await hospitalApi.create(id); await refreshList(); toast.push({ tone: "success", message: `Created ${id}.` }); await select(id); }
    catch (e) { toast.push({ tone: "danger", message: msg(e) }); }
    finally { setBusy(false); }
  }
  async function remove(id: string) {
    setBusy(true);
    try {
      await hospitalApi.remove(id); await refreshList(); toast.push({ tone: "success", message: `Deleted ${id}.` });
      if (selectedId === id) { const active = hospitals.find((h) => h.active); if (active) await select(active.id); else { setSelectedId(null); editor.load(null); } }
    } catch (e) { toast.push({ tone: "danger", message: msg(e) }); }
    finally { setBusy(false); }
  }
  async function save() {
    if (!editor.config || !selectedId) return;
    const found = validateConfig(editor.config);
    setIssues(found);
    if (found.length) { setTab(found[0].tab as TabId); return; }
    setSaving(true); setServerError(null);
    try {
      await hospitalApi.saveJson(selectedId, editor.config);
      editor.markSaved(); await refreshList();
      toast.push({ tone: "success", message: "Configuration saved. Triage rules re-synced." });
    } catch (e) { setServerError(msg(e)); }
    finally { setSaving(false); }
  }

  const selected = hospitals.find((h) => h.id === selectedId);

  return (
    <div className="pb-24">
      <PageHeader title="Clinic configuration" description="Departments, doctors, routing keywords, triage rules and the intake checklist. Changes apply to new cases only." />
      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <HospitalsRail hospitals={hospitals} selectedId={selectedId} busy={busy} hms={initialHms}
          onSelect={select} onActivate={activate} onCreate={create} onDelete={remove} />

        <div className="min-w-0">
          {!selectedId ? (
            <EmptyState icon={<Icons.settings size={20} />} title="Select a clinic" description="Choose a clinic on the left to edit its configuration." />
          ) : (
            <>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-lg font-semibold">{selected?.name ?? selectedId}</h2>
                  <p className="font-mono text-xs text-fg-subtle">{selectedId}{selected?.active ? " · active" : ""}</p>
                </div>
              </div>
              <Tabs tabs={TABS} value={tab} onChange={setTab} className="mb-5 overflow-x-auto" />
              {issues.length ? (
                <Alert tone="warning" title="Fix these before saving" className="mb-4">
                  <ul className="list-disc pl-4">{issues.map((i, k) => <li key={k}>{i.message}</li>)}</ul>
                </Alert>
              ) : null}
              {serverError ? <Alert tone="danger" title="The server rejected the configuration" className="mb-4">{serverError}</Alert> : null}
              {loading ? <div className="space-y-3"><Skeleton className="h-10 w-1/2" /><Skeleton className="h-48" /></div>
                : !editor.config ? <EmptyState title="Configuration unavailable" description="Could not load this clinic." />
                : tab === "general" ? <GeneralTab editor={editor} hospitalId={selectedId} />
                : tab === "departments" ? <DepartmentsTab editor={editor} />
                : tab === "appointments" ? <AppointmentsTab editor={editor} />
                : tab === "routing" ? <RoutingTab editor={editor} />
                : tab === "rules" ? <TriageRulesTab editor={editor} />
                : tab === "fields" ? <IntakeFieldsTab editor={editor} />
                : <AdvancedYamlTab hospitalId={selectedId} onSaved={async () => { editor.load(await hospitalApi.getJson(selectedId)); await refreshList(); }} />}
            </>
          )}
        </div>
      </div>

      {editor.dirty && selectedId ? (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 backdrop-blur">
          <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-3 px-4 py-3 sm:px-6">
            <p className="flex items-center gap-2 text-sm"><span className="h-2 w-2 rounded-full bg-warning" aria-hidden="true" /> Unsaved changes</p>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => { editor.discard(); setIssues([]); setServerError(null); }} disabled={saving}>Discard</Button>
              <Button onClick={save} loading={saving} icon={<Icons.check size={16} />}>Save configuration</Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}