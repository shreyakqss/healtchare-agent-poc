import { ApiError, api, type PatientRoster } from "@/lib/api";
import SimulationView from "./simulation-view";

// The roster is read at request time; the runs themselves are driven entirely
// in the browser from event handlers.
export const dynamic = "force-dynamic";

export default async function SimulationPage() {
  let roster: PatientRoster = { source: "fixture", patients: [] };
  let error: string | null = null;

  try {
    roster = await api.simulationPatients();
  } catch (err) {
    error = err instanceof ApiError ? err.message : String(err);
  }

  return <SimulationView roster={roster} initialError={error} />;
}
