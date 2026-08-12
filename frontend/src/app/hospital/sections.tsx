"use client";

import type { HospitalDoc, TriageRuleDoc } from "@/lib/api";
import {
  Banner,
  Button,
  Empty,
  Panel,
  PriorityTag,
  Tag,
  icons,
  inputClass,
  titleCase,
} from "@/lib/ui";
import {
  AddButton,
  ChipInput,
  EditorCard,
  TextField,
  Toggle,
  type Update,
} from "./builder-parts";
import OrgChart from "./org-chart";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

/** Fields the intake assistant can be asked to collect. */
const KNOWN_INTAKE_FIELDS = [
  ["reason_for_visit", "What brought the patient in"],
  ["symptom", "Presenting symptoms"],
  ["duration", "How long symptoms have lasted"],
  ["name", "The patient's name"],
  ["age", "The patient's age"],
  ["gender", "The patient's gender"],
  ["history", "Existing conditions"],
  ["medication", "Current medications"],
  ["allergy", "Known allergies"],
  ["contact_preference", "How to reach the patient"],
] as const;

/* --- overview ------------------------------------------------------------ */

export function OverviewSection({ doc, update }: { doc: HospitalDoc; update: Update }) {
  const hospital = doc.hospital ?? {};
  const set = (key: string, value: string) =>
    update((draft) => {
      draft.hospital = { ...(draft.hospital ?? {}), [key]: value };
    });

  return (
    <div className="space-y-5">
      <Panel eyebrow="Step 1" title="Hospital information">
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Hospital name"
            value={hospital.name ?? ""}
            onChange={(value) => set("name", value)}
            placeholder="Northside Clinic"
          />
          <TextField
            label="Location"
            value={hospital.location ?? ""}
            onChange={(value) => set("location", value)}
            placeholder="Pune, India"
          />
          <TextField
            label="Timezone"
            value={hospital.timezone ?? ""}
            onChange={(value) => set("timezone", value)}
            placeholder="Asia/Kolkata"
            mono
          />
          <TextField
            label="Identifier"
            value={hospital.id ?? ""}
            onChange={(value) => set("id", value)}
            mono
            hint="Display metadata. The file name is the id the system routes on."
          />
        </div>
      </Panel>

      <Panel eyebrow="Structure" title="Hospital, departments and clinicians">
        <OrgChart doc={doc} />
      </Panel>
    </div>
  );
}

/* --- departments --------------------------------------------------------- */

export function DepartmentsSection({ doc, update }: { doc: HospitalDoc; update: Update }) {
  const departments = doc.departments ?? [];

  return (
    <Panel
      eyebrow="Step 2"
      title="Departments"
      actions={<span className="text-[11px] text-faint">{departments.length}</span>}
    >
      <p className="mb-4 text-xs text-dim">
        Every case is routed to one of these. Exactly one is the fallback for
        anything the routing rules do not match.
      </p>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {departments.map((department, index) => (
          <EditorCard
            key={department.id}
            title={department.name || "Untitled"}
            badge={department.default ? <Tag tone="accent">default</Tag> : undefined}
            onRemove={
              departments.length > 1
                ? () =>
                    update((draft) => {
                      draft.departments = (draft.departments ?? []).filter(
                        (d) => d.id !== department.id,
                      );
                      // Doctors and keyword rules point at this id — drop both
                      // rather than leaving the config referencing a ghost.
                      draft.doctors = (draft.doctors ?? []).filter(
                        (d) => d.department_id !== department.id,
                      );
                      if (draft.specialty_map) delete draft.specialty_map[department.id];
                    })
                : undefined
            }
          >
            <TextField
              label="Name"
              value={department.name}
              onChange={(value) =>
                update((draft) => {
                  draft.departments![index].name = value;
                })
              }
            />
            <p className="font-mono text-[11px] text-faint">id: {department.id}</p>
            <Toggle
              checked={Boolean(department.default)}
              onChange={() =>
                update((draft) => {
                  draft.departments = (draft.departments ?? []).map((d) => ({
                    ...d,
                    default: d.id === department.id,
                  }));
                })
              }
              label="Fallback department"
              hint="Where unmatched cases go"
            />
          </EditorCard>
        ))}
      </div>

      <div className="mt-3">
        <AddButton
          label="Add department"
          onClick={() =>
            update((draft) => {
              const departmentsDraft = draft.departments ?? (draft.departments = []);
              let id = "new_department";
              let n = 1;
              while (departmentsDraft.some((d) => d.id === id))
                id = `new_department_${++n}`;
              departmentsDraft.push({ id, name: "New department" });
            })
          }
        />
      </div>
    </Panel>
  );
}

/* --- doctors ------------------------------------------------------------- */

export function DoctorsSection({ doc, update }: { doc: HospitalDoc; update: Update }) {
  const doctors = doc.doctors ?? [];
  const departments = doc.departments ?? [];

  return (
    <Panel
      eyebrow="Step 3"
      title="Doctors"
      actions={<span className="text-[11px] text-faint">{doctors.length}</span>}
    >
      {departments.length === 0 ? (
        <Empty>Add a department first — every doctor belongs to one.</Empty>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {doctors.map((doctor, index) => (
              <EditorCard
                key={doctor.id}
                title={doctor.name || "Unnamed"}
                onRemove={() =>
                  update((draft) => {
                    draft.doctors = (draft.doctors ?? []).filter((d) => d.id !== doctor.id);
                  })
                }
              >
                <TextField
                  label="Name"
                  value={doctor.name}
                  onChange={(value) =>
                    update((draft) => {
                      draft.doctors![index].name = value;
                    })
                  }
                />
                <label className="block">
                  <span className="eyebrow">Department</span>
                  <select
                    value={doctor.department_id}
                    onChange={(event) =>
                      update((draft) => {
                        draft.doctors![index].department_id = event.target.value;
                      })
                    }
                    className={`${inputClass} mt-1.5`}
                  >
                    {departments.map((department) => (
                      <option key={department.id} value={department.id}>
                        {department.name}
                      </option>
                    ))}
                  </select>
                </label>
                <TextField
                  label="Specialty"
                  value={doctor.specialty ?? ""}
                  onChange={(value) =>
                    update((draft) => {
                      draft.doctors![index].specialty = value;
                    })
                  }
                  placeholder="Interventional cardiology"
                />
                <div>
                  <span className="eyebrow">Working days</span>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {DAYS.map((day) => {
                      const on = (doctor.working_days ?? []).includes(day);
                      return (
                        <button
                          key={day}
                          onClick={() =>
                            update((draft) => {
                              const target = draft.doctors![index];
                              const days = new Set(target.working_days ?? []);
                              if (days.has(day)) days.delete(day);
                              else days.add(day);
                              target.working_days = DAYS.filter((d) => days.has(d));
                            })
                          }
                          className={`rounded border px-2 py-1 text-[11px] uppercase transition-colors ${
                            on
                              ? "border-accent/50 bg-accent/12 text-accent"
                              : "border-line text-faint hover:text-dim"
                          }`}
                        >
                          {day}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <p className="font-mono text-[11px] text-faint">id: {doctor.id}</p>
              </EditorCard>
            ))}
          </div>

          <div className="mt-3">
            <AddButton
              label="Add doctor"
              onClick={() =>
                update((draft) => {
                  const doctorsDraft = draft.doctors ?? (draft.doctors = []);
                  let id = "new_doctor";
                  let n = 1;
                  while (doctorsDraft.some((d) => d.id === id)) id = `new_doctor_${++n}`;
                  doctorsDraft.push({
                    id,
                    name: "New doctor",
                    department_id: departments[0].id,
                    working_days: ["mon", "tue", "wed", "thu", "fri"],
                  });
                })
              }
            />
          </div>
        </>
      )}
    </Panel>
  );
}

/* --- appointment types --------------------------------------------------- */

export function AppointmentsSection({ doc, update }: { doc: HospitalDoc; update: Update }) {
  const types = doc.appointment_types ?? [];

  return (
    <Panel eyebrow="Step 4" title="Appointment types">
      <p className="mb-4 text-xs text-dim">
        What the clinic can offer. Triage priority decides which one a case is
        offered — that mapping lives under Routing.
      </p>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {types.map((type, index) => (
          <EditorCard
            key={type.id}
            title={type.label || "Untitled"}
            onRemove={
              types.length > 1
                ? () =>
                    update((draft) => {
                      draft.appointment_types = (draft.appointment_types ?? []).filter(
                        (t) => t.id !== type.id,
                      );
                    })
                : undefined
            }
          >
            <TextField
              label="Label"
              value={type.label}
              onChange={(value) =>
                update((draft) => {
                  draft.appointment_types![index].label = value;
                })
              }
            />
            <label className="block">
              <span className="eyebrow">Duration (minutes)</span>
              <input
                type="number"
                min={5}
                step={5}
                value={type.duration_minutes ?? 30}
                onChange={(event) =>
                  update((draft) => {
                    draft.appointment_types![index].duration_minutes = Number(
                      event.target.value,
                    );
                  })
                }
                className={`${inputClass} nums mt-1.5`}
              />
            </label>
            <p className="font-mono text-[11px] text-faint">id: {type.id}</p>
          </EditorCard>
        ))}
      </div>

      <div className="mt-3">
        <AddButton
          label="Add appointment type"
          onClick={() =>
            update((draft) => {
              const typesDraft = draft.appointment_types ?? (draft.appointment_types = []);
              let id = "new_type";
              let n = 1;
              while (typesDraft.some((t) => t.id === id)) id = `new_type_${++n}`;
              typesDraft.push({ id, label: "New appointment type", duration_minutes: 20 });
            })
          }
        />
      </div>
    </Panel>
  );
}

/* --- routing ------------------------------------------------------------- */

export function RoutingSection({ doc, update }: { doc: HospitalDoc; update: Update }) {
  const departments = doc.departments ?? [];
  const map = doc.specialty_map ?? {};
  const priorityMap = doc.priority_appointment_map ?? {};
  const types = doc.appointment_types ?? [];

  return (
    <div className="space-y-5">
      <Panel eyebrow="Step 5" title="Routing rules">
        <p className="mb-4 text-xs text-dim">
          Keyword match against what the patient reported. The first department
          whose keywords match wins; anything unmatched goes to the fallback
          department.
        </p>

        <div className="space-y-3">
          {departments
            .filter((department) => !department.default)
            .map((department) => (
              <div
                key={department.id}
                className="grid items-center gap-3 rounded-md border border-line bg-surface/70 p-4 lg:grid-cols-[minmax(0,1fr)_auto_14rem]"
              >
                <div>
                  <p className="eyebrow mb-1.5">
                    <span className="text-accent">IF</span> reported symptoms contain
                  </p>
                  <ChipInput
                    values={map[department.id] ?? []}
                    tone="info"
                    placeholder="chest pain…"
                    onChange={(values) =>
                      update((draft) => {
                        draft.specialty_map = {
                          ...(draft.specialty_map ?? {}),
                          [department.id]: values,
                        };
                      })
                    }
                  />
                </div>
                <icons.chevron className="hidden text-[18px] text-line lg:block" />
                <div className="rounded border border-accent/25 bg-accent/6 px-3 py-2.5">
                  <p className="eyebrow mb-1">
                    <span className="text-accent">THEN</span> route to
                  </p>
                  <p className="text-sm font-medium text-text">{department.name}</p>
                </div>
              </div>
            ))}
        </div>

        {departments.some((d) => d.default) && (
          <p className="mt-3 flex items-center gap-2 rounded border border-dashed border-line px-4 py-2.5 text-xs text-faint">
            <icons.route className="text-[14px]" />
            Anything unmatched routes to{" "}
            <span className="text-dim">
              {departments.find((d) => d.default)?.name}
            </span>
            .
          </p>
        )}
      </Panel>

      <Panel eyebrow="Scheduling" title="Priority → appointment type">
        <div className="grid gap-3 sm:grid-cols-3">
          {(["high", "medium", "low"] as const).map((priority) => (
            <div key={priority} className="rounded border border-line bg-surface/70 p-3.5">
              <PriorityTag priority={priority} />
              <select
                value={priorityMap[priority] ?? ""}
                onChange={(event) =>
                  update((draft) => {
                    draft.priority_appointment_map = {
                      ...(draft.priority_appointment_map ?? {}),
                      [priority]: event.target.value,
                    };
                  })
                }
                className={`${inputClass} mt-2.5`}
              >
                {types.map((type) => (
                  <option key={type.id} value={type.id}>
                    {type.label}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

/* --- triage rules -------------------------------------------------------- */

export function TriageSection({ doc, update }: { doc: HospitalDoc; update: Update }) {
  const rules = doc.triage_rules?.rules ?? [];
  const departments = doc.departments ?? [];

  const isFallback = (rule: TriageRuleDoc) =>
    Object.keys(rule.condition ?? {}).length === 0;

  const setRule = (index: number, mutate: (rule: TriageRuleDoc) => void) =>
    update((draft) => {
      mutate(draft.triage_rules!.rules![index]);
    });

  return (
    <Panel
      eyebrow="Step 6"
      title="Triage rules"
      actions={
        <span className="text-[11px] text-faint">
          v{doc.triage_rules?.version ?? "—"} · {rules.length} rules
        </span>
      }
    >
      <div className="mb-4 space-y-2">
        <p className="text-xs text-dim">
          These decide administrative urgency only — how soon someone is seen, never
          what is wrong with them. Rules are evaluated top to bottom and the first
          match wins.
        </p>
        <Banner tone="warn">
          One rule must have no conditions at all. It is the fallback that
          guarantees every case gets a priority, and it cannot be removed.
        </Banner>
      </div>

      <div className="space-y-3">
        {rules.map((rule, index) => {
          const fallback = isFallback(rule);
          return (
            <EditorCard
              key={rule.code}
              title={
                <span className="font-mono text-xs text-accent">{rule.code}</span>
              }
              badge={
                <span className="flex items-center gap-2">
                  <PriorityTag priority={rule.priority} />
                  {fallback && <Tag tone="med">fallback</Tag>}
                </span>
              }
              onRemove={
                fallback
                  ? undefined
                  : () =>
                      update((draft) => {
                        draft.triage_rules!.rules = draft.triage_rules!.rules!.filter(
                          (r) => r.code !== rule.code,
                        );
                      })
              }
            >
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto_18rem]">
                <div className="space-y-3">
                  <p className="eyebrow">
                    <span className="text-accent">IF</span>{" "}
                    {fallback ? "nothing above matched" : "the case shows"}
                  </p>

                  {fallback ? (
                    <p className="rounded border border-dashed border-line px-3 py-4 text-center text-xs text-faint">
                      No conditions — this rule always matches.
                    </p>
                  ) : (
                    <>
                      <div>
                        <span className="text-[11px] text-faint">
                          Any of these symptoms
                        </span>
                        <ChipInput
                          values={rule.condition.any_symptom ?? []}
                          tone="high"
                          onChange={(values) =>
                            setRule(index, (target) => {
                              if (values.length) target.condition.any_symptom = values;
                              else delete target.condition.any_symptom;
                            })
                          }
                        />
                      </div>
                      <div>
                        <span className="text-[11px] text-faint">
                          AND any of these existing conditions
                        </span>
                        <ChipInput
                          values={rule.condition.any_history ?? []}
                          tone="med"
                          onChange={(values) =>
                            setRule(index, (target) => {
                              if (values.length) target.condition.any_history = values;
                              else delete target.condition.any_history;
                            })
                          }
                        />
                      </div>
                      <div className="grid gap-2 sm:grid-cols-2">
                        <label className="block">
                          <span className="text-[11px] text-faint">
                            Symptom lasting at least (days)
                          </span>
                          <input
                            type="number"
                            min={0}
                            value={rule.condition.min_duration_days ?? ""}
                            placeholder="—"
                            onChange={(event) =>
                              setRule(index, (target) => {
                                const value = Number(event.target.value);
                                if (event.target.value === "" || Number.isNaN(value))
                                  delete target.condition.min_duration_days;
                                else target.condition.min_duration_days = value;
                              })
                            }
                            className={`${inputClass} nums mt-1`}
                          />
                        </label>
                        <div className="self-end">
                          <Toggle
                            checked={Boolean(rule.condition.allergy_conflict)}
                            onChange={(checked) =>
                              setRule(index, (target) => {
                                if (checked) target.condition.allergy_conflict = true;
                                else delete target.condition.allergy_conflict;
                              })
                            }
                            label="Allergy conflicts a medication"
                          />
                        </div>
                      </div>
                    </>
                  )}
                </div>

                <icons.chevron className="hidden self-center text-[18px] text-line lg:block" />

                <div className="space-y-3">
                  <p className="eyebrow">
                    <span className="text-accent">THEN</span> set
                  </p>
                  <label className="block">
                    <span className="text-[11px] text-faint">Priority</span>
                    <select
                      value={rule.priority}
                      onChange={(event) =>
                        setRule(index, (target) => {
                          target.priority = event.target.value;
                        })
                      }
                      className={`${inputClass} mt-1`}
                    >
                      {["high", "medium", "low"].map((priority) => (
                        <option key={priority} value={priority}>
                          {titleCase(priority)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block">
                    <span className="text-[11px] text-faint">Suggested department</span>
                    <select
                      value={rule.specialty_hint ?? ""}
                      onChange={(event) =>
                        setRule(index, (target) => {
                          if (event.target.value) target.specialty_hint = event.target.value;
                          else delete target.specialty_hint;
                        })
                      }
                      className={`${inputClass} mt-1`}
                    >
                      <option value="">Let routing decide</option>
                      {departments.map((department) => (
                        <option key={department.id} value={department.id}>
                          {department.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block">
                    <span className="text-[11px] text-faint">Staff action</span>
                    <textarea
                      value={rule.action ?? ""}
                      rows={2}
                      onChange={(event) =>
                        setRule(index, (target) => {
                          target.action = event.target.value;
                        })
                      }
                      className={`${inputClass} mt-1 resize-y`}
                    />
                  </label>
                  <label className="block">
                    <span className="text-[11px] text-faint">
                      Explanation shown to staff
                    </span>
                    <textarea
                      value={rule.explanation ?? ""}
                      rows={2}
                      onChange={(event) =>
                        setRule(index, (target) => {
                          target.explanation = event.target.value;
                        })
                      }
                      className={`${inputClass} mt-1 resize-y`}
                    />
                  </label>
                </div>
              </div>
            </EditorCard>
          );
        })}
      </div>

      <div className="mt-3">
        <AddButton
          label="Add triage rule"
          onClick={() =>
            update((draft) => {
              const rulesDraft = draft.triage_rules?.rules;
              if (!rulesDraft) return;
              // Keep the no-condition fallback last: evaluation is top-down.
              const next = rulesDraft.filter(
                (r) => Object.keys(r.condition ?? {}).length > 0,
              );
              const fallbackRules = rulesDraft.filter(
                (r) => Object.keys(r.condition ?? {}).length === 0,
              );
              let code = `TR-HIGH-${String(next.length + 1).padStart(3, "0")}`;
              let n = next.length + 1;
              while (rulesDraft.some((r) => r.code === code))
                code = `TR-HIGH-${String(++n).padStart(3, "0")}`;
              next.push({
                code,
                priority: "high",
                condition: { any_symptom: [] },
                action: "Route to an urgent same-day slot.",
                explanation: "A symptom on the clinic's escalation list was reported.",
              });
              draft.triage_rules!.rules = [...next, ...fallbackRules];
            })
          }
        />
      </div>
    </Panel>
  );
}

/* --- intake fields ------------------------------------------------------- */

export function IntakeSection({ doc, update }: { doc: HospitalDoc; update: Update }) {
  const required = doc.required_intake_fields ?? [];
  // Anything a clinic already requires but this UI does not know about still
  // shows up, so a hand-edited config is never silently dropped.
  const extra = required.filter(
    (field) => !KNOWN_INTAKE_FIELDS.some(([key]) => key === field),
  );

  const toggle = (field: string, on: boolean) =>
    update((draft) => {
      const current = new Set(draft.required_intake_fields ?? []);
      if (on) current.add(field);
      else current.delete(field);
      draft.required_intake_fields = [...current];
    });

  return (
    <Panel eyebrow="Step 7" title="Required intake fields">
      <p className="mb-4 text-xs text-dim">
        The assistant keeps asking until each of these is answered, and
        pre-screening reports whatever is still missing.
      </p>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {[...KNOWN_INTAKE_FIELDS, ...extra.map((field) => [field, "Custom field"] as const)].map(
          ([field, hint]) => (
            <Toggle
              key={field}
              checked={required.includes(field)}
              onChange={(checked) => toggle(field, checked)}
              label={titleCase(field)}
              hint={hint}
            />
          ),
        )}
      </div>
    </Panel>
  );
}

/* --- developer ----------------------------------------------------------- */

export function DeveloperSection({
  hospitalId,
  yamlText,
  onYamlChange,
  onSaveYaml,
  dirty,
  busy,
}: {
  hospitalId: string;
  yamlText: string;
  onYamlChange: (text: string) => void;
  onSaveYaml: () => void;
  dirty: boolean;
  busy: boolean;
}) {
  function download() {
    const blob = new Blob([yamlText], { type: "text/yaml" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${hospitalId}.yaml`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Panel
      eyebrow="Developer"
      title="Raw configuration"
      actions={
        <div className="flex items-center gap-2">
          {dirty && <span className="text-[11px] text-med">unsaved</span>}
          <Button onClick={() => void navigator.clipboard.writeText(yamlText)}>
            Copy
          </Button>
          <Button onClick={download}>Export</Button>
          <label className="inline-flex cursor-pointer items-center gap-2 rounded border border-line px-3 py-1.5 text-sm text-dim transition-colors hover:border-faint hover:text-text">
            Import
            <input
              type="file"
              accept=".yaml,.yml,text/yaml"
              className="hidden"
              onChange={async (event) => {
                const file = event.target.files?.[0];
                if (file) onYamlChange(await file.text());
                event.target.value = "";
              }}
            />
          </label>
          <Button variant="primary" onClick={onSaveYaml} disabled={busy || !dirty}>
            Save YAML
          </Button>
        </div>
      }
    >
      <p className="mb-3 text-xs text-dim">
        The same file the visual editor writes. Saving validates first — a config
        with no departments, no triage rules, or no fallback rule is rejected and
        never reaches disk.
      </p>
      <textarea
        value={yamlText}
        onChange={(event) => onYamlChange(event.target.value)}
        spellCheck={false}
        rows={30}
        className={`${inputClass} resize-y font-mono text-xs leading-relaxed`}
      />
      <p className="mt-2 flex items-center gap-2 text-[11px] text-faint">
        <icons.code className="text-[13px]" />
        Editing here and saving through the visual builder afterwards will drop the
        file&apos;s comments — the builder round-trips the document, not the text.
      </p>
    </Panel>
  );
}
