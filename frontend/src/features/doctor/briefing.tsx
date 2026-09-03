import type { CaseDetail } from "@/lib/api";

export interface BriefingSections {
  chief_complaint?: string;
  reported_symptoms?: string[];
  relevant_history?: string[];
  medications?: string[];
  allergies?: string[];
  context_for_clinician?: string;
  missing_information?: string[];
}

export function briefingOf(c: CaseDetail): BriefingSections {
  return (c.prescreening_summary?.sections ?? {}) as BriefingSections;
}
