/**
 * Which visits belong to the person at this browser.
 *
 * There is no patient account in this POC — the backend has no patient table,
 * no login, and `GET /cases` returns every case in the clinic. So "my visits"
 * cannot be asked of the server; the only thing that knows is the browser that
 * opened them. This module is that memory: case ids in `localStorage`, written
 * when a session starts and read when the patient opens their records.
 *
 * The consequences are real and deliberately not hidden from the patient UI:
 * clearing site data loses the list, and another device shows nothing. The
 * cases themselves are untouched — a clinician still sees them all. Replacing
 * this with a real identity means a patient id on `PatientCase` and a
 * `GET /patients/{id}/cases`, at which point every caller here becomes an API
 * call and the surfaces above it do not change.
 */

const KEY = "healthcare.patient.cases";

/** One remembered visit. The label is a fallback for before the case loads. */
export type RememberedCase = {
  caseId: string;
  sessionId: string;
  /** ISO timestamp written when this browser opened the case. */
  startedAt: string;
};

const isBrowser = () => typeof window !== "undefined";

/** Newest first. Silent on unreadable storage — history is never load-bearing. */
export function rememberedCases(): RememberedCase[] {
  if (!isBrowser()) return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (entry): entry is RememberedCase =>
          typeof entry === "object" &&
          entry !== null &&
          typeof (entry as RememberedCase).caseId === "string",
      )
      .sort((a, b) => b.startedAt.localeCompare(a.startedAt));
  } catch {
    // Private mode, disabled storage, or something else wrote the key.
    return [];
  }
}

/** Records a visit as this patient's. Idempotent — re-opening does not duplicate. */
export function rememberCase(entry: RememberedCase): void {
  if (!isBrowser()) return;
  try {
    const existing = rememberedCases().filter((c) => c.caseId !== entry.caseId);
    window.localStorage.setItem(KEY, JSON.stringify([entry, ...existing]));
  } catch {
    // Storage is full or blocked. The visit still happened and the clinician
    // still has it; only this browser's shortcut to it is lost.
  }
}

/** Forget every remembered visit on this device. The cases themselves remain. */
export function forgetCases(): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* nothing to do — the list is a convenience */
  }
}
