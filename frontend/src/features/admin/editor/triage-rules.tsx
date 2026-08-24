"use client";

import type { HospitalConfig, Priority, TriageRuleConfig } from "@/lib/api/types";
import { PRIORITY_LABEL } from "@/lib/constants";
import { Alert, Badge, Button, Card, CardBody, CardHeader, Field, Icons, IconButton, Input, PriorityBadge, Segmented, Select, Textarea } from "@/components/ui";
import { ChipInput } from "@/features/admin/chip-input";
import { isFallbackRule } from "@/features/admin/validate";
import type { ConfigEditor } from "@/features/admin/use-config-editor";

const ORDER: Record<Priority, number> = { high: 0, medium: 1, low: 2 };
type Cond = TriageRuleConfig["condition"];

export function TriageRulesTab({ editor }: { editor: ConfigEditor }) {
  const cfg = editor.config as HospitalConfig;
  const rules = cfg.triage_rules?.rules ?? [];
  const deps = cfg.departments ?? [];
  const hasFallback = rules.some((r) => isFallbackRule(r.condition));
  const indexed = rules.map((r, i) => ({ r, i })).sort((a, b) => ORDER[a.r.priority] - ORDER[b.r.priority] || a.r.code.localeCompare(b.r.code));

  const setRules = (next: TriageRuleConfig[]) => editor.update((c) => ({ ...c, triage_rules: { ...c.triage_rules, rules: next } }));
  const edit = (i: number, patch: Partial<TriageRuleConfig>) => setRules(rules.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const editCond = (i: number, fn: (c: Cond) => Cond) => {
    const next = fn({ ...(rules[i].condition ?? {}) });
    for (const k of Object.keys(next) as (keyof Cond)[]) {
      const v = next[k];
      if (v === undefined || v === false || (Array.isArray(v) && v.length === 0)) delete next[k];
    }
    edit(i, { condition: next });
  };

  return (
    <div className="space-y-4">
      <Alert tone="info" title="Administrative urgency only">
        Rules decide how soon someone is seen and by which desk. They never decide what is wrong with them. They are evaluated high, then medium, then low, and the
        first match wins. The language model only writes the briefing; it cannot change a priority.
      </Alert>
      {!hasFallback ? <Alert tone="danger" title="No fallback rule">Add a rule with no conditions (usually low priority) so every case receives a priority. The server refuses to save without one.</Alert> : null}

      <div className="flex flex-wrap items-end justify-between gap-3">
        <Field label="Rule set version" htmlFor="rule-version" hint="Recorded on every triage result for auditability." className="w-56">
          <Input id="rule-version" value={cfg.triage_rules?.version ?? ""} onChange={(e) => editor.update((c) => ({ ...c, triage_rules: { ...c.triage_rules, version: e.target.value } }))} />
        </Field>
        <Button variant="secondary" icon={<Icons.plus size={14} />}
          onClick={() => setRules([...rules, { code: `TR-MED-${String(rules.length + 1).padStart(3, "0")}`, priority: "medium", condition: {}, action: "", explanation: "" }])}>
          Add rule
        </Button>
      </div>

      {indexed.map(({ r, i }) => {
        const fallback = isFallbackRule(r.condition);
        const c = r.condition ?? {};
        return (
          <Card key={i}>
            <CardHeader
              title={<span className="flex items-center gap-2 font-mono text-sm">{r.code || "(no code)"} <PriorityBadge priority={r.priority} /> {fallback ? <Badge tone="info">Fallback</Badge> : null}</span>}
              action={<IconButton size="sm" label="Remove rule" icon={<Icons.trash size={14} />} onClick={() => setRules(rules.filter((_, j) => j !== i))} />}
            />
            <CardBody className="grid gap-4 lg:grid-cols-2">
              <div className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Code" htmlFor={`code-${i}`} required>
                    <Input id={`code-${i}`} value={r.code} className="font-mono" onChange={(e) => edit(i, { code: e.target.value.toUpperCase() })} />
                  </Field>
                  <Field label="Priority" htmlFor={`prio-${i}`}>
                    <Segmented label="Priority" value={r.priority} onChange={(v) => edit(i, { priority: v })}
                      options={(["high", "medium", "low"] as Priority[]).map((p) => ({ value: p, label: PRIORITY_LABEL[p] }))} />
                  </Field>
                </div>
                <Field label="Explanation" htmlFor={`expl-${i}`} hint="Shown to the clinician as the reason the rule fired.">
                  <Textarea id={`expl-${i}`} rows={2} className="min-h-16" value={r.explanation} onChange={(e) => edit(i, { explanation: e.target.value })} />
                </Field>
                <Field label="Action" htmlFor={`act-${i}`} hint="The administrative next step.">
                  <Textarea id={`act-${i}`} rows={2} className="min-h-16" value={r.action} onChange={(e) => edit(i, { action: e.target.value })} />
                </Field>
                <Field label="Specialty hint" htmlFor={`hint-${i}`} hint="Overrides keyword routing when this rule fires.">
                  <Select id={`hint-${i}`} value={r.specialty_hint ?? ""} onChange={(e) => edit(i, { specialty_hint: e.target.value || undefined })}>
                    <option value="">None</option>
                    {deps.map((d) => <option key={d.id} value={d.id}>{d.name || d.id}</option>)}
                  </Select>
                </Field>
              </div>

              <fieldset className="space-y-3 rounded-md border border-line bg-sunken/60 p-4">
                <legend className="px-1 text-xs font-semibold uppercase tracking-wider text-fg-subtle">Conditions (all must hold)</legend>
                <CondChips label="Any of these symptoms" value={c.any_symptom ?? []} onChange={(v) => editCond(i, (x) => ({ ...x, any_symptom: v }))} />
                <CondChips label="All of these symptoms" value={c.all_symptoms ?? []} onChange={(v) => editCond(i, (x) => ({ ...x, all_symptoms: v }))} />
                <CondChips label="Any of these history items" value={c.any_history ?? []} onChange={(v) => editCond(i, (x) => ({ ...x, any_history: v }))} />
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Minimum duration (days)" htmlFor={`dur-${i}`} hint="Leave empty to ignore duration.">
                    <Input id={`dur-${i}`} type="number" min={0} className="tabular" value={c.min_duration_days ?? ""}
                      onChange={(e) => editCond(i, (x) => ({ ...x, min_duration_days: e.target.value === "" ? undefined : Number(e.target.value) }))} />
                  </Field>
                  <label className="mt-6 flex items-center gap-2 text-sm">
                    <input type="checkbox" className="h-4 w-4 accent-brand" checked={!!c.allergy_conflict} onChange={(e) => editCond(i, (x) => ({ ...x, allergy_conflict: e.target.checked || undefined }))} />
                    Allergy / medication conflict reported
                  </label>
                </div>
                {fallback ? <p className="text-xs text-fg-muted">No conditions: this rule matches every case that nothing above it caught.</p> : null}
              </fieldset>
            </CardBody>
          </Card>
        );
      })}
    </div>
  );
}

function CondChips({ label, value, onChange }: { label: string; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div>
      <p className="mb-1.5 text-sm font-medium">{label}</p>
      <ChipInput label={label} value={value} onChange={onChange} placeholder="Type a keyword, press Enter" />
    </div>
  );
}