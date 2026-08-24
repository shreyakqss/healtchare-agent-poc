import type { HospitalConfig } from "@/lib/api/types";

export interface ValidationIssue { tab: string; message: string }

export function isFallbackRule(condition: HospitalConfig["triage_rules"]["rules"][number]["condition"] | undefined): boolean {
  if (!condition) return true;
  const c = condition;
  return !(c.any_symptom?.length || c.all_symptoms?.length || c.any_history?.length || c.min_duration_days !== undefined || c.allergy_conflict);
}

export function validateConfig(cfg: HospitalConfig): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  if (!cfg.hospital?.name?.trim()) issues.push({ tab: "general", message: "The clinic needs a display name." });

  const deps = cfg.departments ?? [];
  if (deps.length === 0) issues.push({ tab: "departments", message: "Add at least one department. Without one, there is nowhere to route a case." });
  const defaults = deps.filter((d) => d.default).length;
  if (deps.length && defaults !== 1) issues.push({ tab: "departments", message: "Exactly one department must be marked as the default." });
  if (deps.some((d) => !d.id.trim() || !d.name.trim())) issues.push({ tab: "departments", message: "Every department needs an id and a name." });
  if (new Set(deps.map((d) => d.id)).size !== deps.length) issues.push({ tab: "departments", message: "Department ids must be unique." });

  const docs = cfg.doctors ?? [];
  if (docs.some((d) => !d.id.trim() || !d.name.trim())) issues.push({ tab: "departments", message: "Every doctor needs an id and a name." });
  if (docs.some((d) => !deps.find((x) => x.id === d.department_id))) issues.push({ tab: "departments", message: "Every doctor must belong to an existing department." });

  const types = cfg.appointment_types ?? [];
  if (types.length === 0) issues.push({ tab: "appointments", message: "Add at least one appointment type." });
  for (const p of ["high", "medium", "low"] as const) {
    if (!types.find((t) => t.id === cfg.priority_appointment_map?.[p])) issues.push({ tab: "appointments", message: `Priority "${p}" is not mapped to an existing appointment type.` });
  }

  const rules = cfg.triage_rules?.rules ?? [];
  if (rules.length === 0) issues.push({ tab: "rules", message: "Add at least one triage rule." });
  if (rules.length && !rules.some((r) => isFallbackRule(r.condition))) issues.push({ tab: "rules", message: "Add a fallback rule (empty condition) so every case receives a priority." });
  if (rules.some((r) => !r.code.trim())) issues.push({ tab: "rules", message: "Every rule needs a code." });
  if (new Set(rules.map((r) => r.code)).size !== rules.length) issues.push({ tab: "rules", message: "Rule codes must be unique." });

  if (!(cfg.required_intake_fields ?? []).length) issues.push({ tab: "fields", message: "Add at least one required intake field." });
  return issues;
}

export const HOSPITAL_ID_PATTERN = /^[a-z0-9][a-z0-9-]{1,62}$/;