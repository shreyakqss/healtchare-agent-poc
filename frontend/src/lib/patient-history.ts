/** Cases started from this browser. There is no patient account in the POC, so this is the only "my visits" there is. */

const KEY = "careflow.patient.cases";

export interface VisitRef { caseId: string; createdAt: string }

export function listVisits(): VisitRef[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw ? (JSON.parse(raw) as VisitRef[]) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function rememberVisit(caseId: string, createdAt: string): void {
  if (typeof window === "undefined") return;
  try {
    const all = listVisits().filter((v) => v.caseId !== caseId);
    localStorage.setItem(KEY, JSON.stringify([{ caseId, createdAt }, ...all].slice(0, 20)));
  } catch {
    /* storage unavailable */
  }
}