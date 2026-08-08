"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  ApiError,
  api,
  type HospitalDoc,
  type HospitalSummary,
} from "@/lib/api";
import {
  Banner,
  Button,
  Dot,
  PageHeader,
  Tag,
  icons,
  inputClass,
} from "@/lib/ui";
import type { Update } from "./builder-parts";
import {
  AppointmentsSection,
  DepartmentsSection,
  DeveloperSection,
  DoctorsSection,
  IntakeSection,
  OverviewSection,
  RoutingSection,
  TriageSection,
} from "./sections";

/**
 * The clinic configuration UI.
 *
 * The visual editor is the primary surface: it edits the parsed config as a
 * document and the backend serialises it. The raw YAML is still reachable
 * under Developer, because a POC config is often faster to paste than to click
 * — but nobody is made to learn YAML to add a doctor.
 */

const SECTIONS = [
  ["overview", "Overview", "grid"],
  ["departments", "Departments", "building"],
  ["doctors", "Doctors", "stethoscope"],
  ["appointments", "Appointments", "clock"],
  ["routing", "Routing", "route"],
  ["triage", "Triage rules", "shield"],
  ["intake", "Intake", "file"],
  ["developer", "Developer", "code"],
] as const;

type SectionKey = (typeof SECTIONS)[number][0];

export default function HospitalBuilder({
  initialHospitals,
  initialDoc,
  initialYaml,
  initialSelected,
  initialError,
}: {
  initialHospitals: HospitalSummary[];
  initialDoc: HospitalDoc | null;
  initialYaml: string;
  initialSelected: string;
  initialError: string | null;
}) {
  const router = useRouter();
  const [hospitals, setHospitals] = useState(initialHospitals);
  const [selected, setSelected] = useState(initialSelected);
  const [section, setSection] = useState<SectionKey>("overview");

  const [doc, setDoc] = useState<HospitalDoc | null>(initialDoc);
  const [savedDoc, setSavedDoc] = useState(JSON.stringify(initialDoc));
  const [yamlText, setYamlText] = useState(initialYaml);
  const [savedYaml, setSavedYaml] = useState(initialYaml);

  const [newId, setNewId] = useState("");
  const [error, setError] = useState(initialError);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const docDirty = JSON.stringify(doc) !== savedDoc;
  const yamlDirty = yamlText !== savedYaml;
  const dirty = docDirty || yamlDirty;
  const activeId = hospitals.find((h) => h.active)?.id ?? "";

  /** Edit a cloned draft — never mutate the rendered document in place. */
  const update: Update = (mutate) =>
    setDoc((current) => {
      if (!current) return current;
      const draft = structuredClone(current);
      mutate(draft);
      return draft;
    });

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setNotice(await action());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  /** Pull both representations back from disk so they cannot drift. */
  async function reload(hospitalId: string) {
    const [list, json, yaml] = await Promise.all([
      api.listHospitals(),
      api.hospitalJson(hospitalId),
      api.hospitalYaml(hospitalId),
    ]);
    setHospitals(list);
    setSelected(hospitalId);
    setDoc(json.config);
    setSavedDoc(JSON.stringify(json.config));
    setYamlText(yaml.yaml_text);
    setSavedYaml(yaml.yaml_text);
    // Other pages render against the active clinic.
    router.refresh();
  }

  function select(id: string) {
    if (dirty && !confirm("Discard unsaved changes to this configuration?")) return;
    void run(async () => {
      await reload(id);
      return `Showing ${id}.`;
    });
  }

  function saveVisual() {
    if (!doc) return;
    void run(async () => {
      await api.saveHospitalJson(selected, doc);
      await reload(selected);
      return `Saved ${selected} and re-synced its triage rules.`;
    });
  }

  function saveYaml() {
    void run(async () => {
      await api.saveHospitalYaml(selected, yamlText);
      await reload(selected);
      return `Saved ${selected} from raw YAML.`;
    });
  }

  const summary = hospitals.find((h) => h.id === selected);

  return (
    <>
      <PageHeader
        eyebrow="Configuration"
        title="Hospital Builder"
        subtitle="Departments, clinicians, routing and triage rules for the clinic this demo runs as. Everything here drives the agents at runtime."
        actions={
          <>
            {dirty && (
              <span className="flex items-center gap-1.5 text-xs text-med">
                <Dot tone="med" live />
                unsaved changes
              </span>
            )}
            <Button
              variant="primary"
              onClick={section === "developer" ? saveYaml : saveVisual}
              disabled={busy || !dirty || !doc}
            >
              {busy ? "Saving…" : "Save configuration"}
            </Button>
          </>
        }
      />

      <div className="space-y-3">
        {error && <Banner tone="error">{error}</Banner>}
        {notice && !error && <Banner tone="ok">{notice}</Banner>}
      </div>

      <div className="mt-5 grid items-start gap-5 lg:grid-cols-[16rem_minmax(0,1fr)]">
        {/* --- clinics + section nav ------------------------------------- */}
        <aside className="space-y-5 lg:sticky lg:top-20">
          <div className="rounded-md border border-line bg-surface/80">
            <p className="eyebrow border-b border-line-soft px-4 py-2.5">Clinics</p>
            <ul className="p-2">
              {hospitals.map((hospital) => (
                <li key={hospital.id}>
                  <button
                    onClick={() => select(hospital.id)}
                    disabled={busy}
                    className={`w-full rounded px-2.5 py-2 text-left transition-colors disabled:opacity-50 ${
                      hospital.id === selected ? "bg-raised" : "hover:bg-raised/60"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-text">
                        {hospital.name}
                      </span>
                      {hospital.active && <Tag tone="accent">active</Tag>}
                    </span>
                    <span className="mt-0.5 block font-mono text-[10px] text-faint">
                      {hospital.id}
                    </span>
                    <span className="mt-0.5 block text-[11px] text-faint">
                      {hospital.departments} depts · {hospital.doctors} doctors ·{" "}
                      {hospital.rules} rules
                    </span>
                  </button>
                  {hospital.id === selected && !hospital.active && (
                    <div className="flex gap-3 px-2.5 pb-2 pt-1 text-[11px]">
                      <button
                        onClick={() =>
                          void run(async () => {
                            await api.activateHospital(hospital.id);
                            await reload(hospital.id);
                            return `${hospital.id} is now the active clinic.`;
                          })
                        }
                        disabled={busy}
                        className="text-accent underline underline-offset-2"
                      >
                        Activate
                      </button>
                      <button
                        onClick={() => {
                          if (!confirm(`Delete the configuration for ${hospital.id}?`))
                            return;
                          void run(async () => {
                            await api.deleteHospital(hospital.id);
                            await reload(activeId);
                            return `Deleted ${hospital.id}.`;
                          });
                        }}
                        disabled={busy}
                        className="text-high underline underline-offset-2"
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
            <div className="border-t border-line-soft p-3">
              <span className="eyebrow">Add a clinic</span>
              <div className="mt-1.5 flex gap-2">
                <input
                  value={newId}
                  onChange={(event) => setNewId(event.target.value)}
                  placeholder="northside-clinic"
                  pattern="[a-z0-9][a-z0-9_-]*"
                  className={`${inputClass} font-mono text-xs`}
                />
                <Button
                  onClick={() =>
                    void run(async () => {
                      const id = newId.trim();
                      await api.createHospital(id);
                      setNewId("");
                      await reload(id);
                      return `Created ${id} as a copy of the active clinic.`;
                    })
                  }
                  disabled={busy || !newId.trim()}
                  className="shrink-0"
                >
                  <icons.plus className="text-[15px]" />
                </Button>
              </div>
              <p className="mt-1.5 text-[11px] leading-4 text-faint">
                Copies the active clinic so it starts valid. Lowercase — it becomes
                the file name.
              </p>
            </div>
          </div>

          <nav className="rounded-md border border-line bg-surface/80 p-2">
            {SECTIONS.map(([key, label, icon]) => {
              const Glyph = icons[icon];
              const isCurrent = section === key;
              return (
                <button
                  key={key}
                  onClick={() => setSection(key)}
                  className={`flex w-full items-center gap-2.5 rounded px-2.5 py-2 text-left text-sm transition-colors ${
                    isCurrent
                      ? "bg-accent/10 text-accent"
                      : "text-dim hover:bg-raised hover:text-text"
                  }`}
                >
                  <Glyph className="text-[15px]" />
                  {label}
                  {key === "developer" && (
                    <span className="ml-auto text-[10px] text-faint">YAML</span>
                  )}
                </button>
              );
            })}
          </nav>
        </aside>

        {/* --- the editor ------------------------------------------------ */}
        <div>
          {summary && (
            <div className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-md border border-line bg-surface/60 px-5 py-3">
              <div>
                <p className="eyebrow">Editing</p>
                <p className="font-mono text-sm text-text">{selected}</p>
              </div>
              {selected !== activeId ? (
                <Tag tone="med">not the active clinic</Tag>
              ) : (
                <Tag tone="accent">
                  <Dot tone="accent" />
                  live — new cases route against this
                </Tag>
              )}
              <span className="ml-auto text-[11px] text-faint">
                triage rules v{doc?.triage_rules?.version ?? "—"}
              </span>
            </div>
          )}

          {!doc ? (
            <Banner tone="error">
              No configuration loaded. Start the backend and reload.
            </Banner>
          ) : section === "overview" ? (
            <OverviewSection doc={doc} update={update} />
          ) : section === "departments" ? (
            <DepartmentsSection doc={doc} update={update} />
          ) : section === "doctors" ? (
            <DoctorsSection doc={doc} update={update} />
          ) : section === "appointments" ? (
            <AppointmentsSection doc={doc} update={update} />
          ) : section === "routing" ? (
            <RoutingSection doc={doc} update={update} />
          ) : section === "triage" ? (
            <TriageSection doc={doc} update={update} />
          ) : section === "intake" ? (
            <IntakeSection doc={doc} update={update} />
          ) : (
            <DeveloperSection
              hospitalId={selected}
              yamlText={yamlText}
              onYamlChange={setYamlText}
              onSaveYaml={saveYaml}
              dirty={yamlDirty}
              busy={busy}
            />
          )}

          {docDirty && section !== "developer" && (
            <div className="mt-4 flex items-center gap-3 rounded-md border border-med/30 bg-med/8 px-4 py-3 text-sm text-med">
              <icons.alert className="shrink-0 text-[16px]" />
              Changes are not saved yet. Saving validates the config first — an
              invalid clinic is rejected and never written.
              <Button
                variant="primary"
                onClick={saveVisual}
                disabled={busy}
                className="ml-auto shrink-0"
              >
                Save configuration
              </Button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
