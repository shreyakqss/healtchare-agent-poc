import { api, type CaseListItem, type HospitalConfig } from "@/lib/api";
import { DEMO_CASES, DEMO_CONFIG } from "@/lib/demo";
import DashboardView from "./dashboard-view";

// Live case state — never prerendered.
export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  let cases: CaseListItem[] = [];
  let config: HospitalConfig | null = null;
  let demo = false;

  try {
    // The roster comes from the active clinic's YAML, the workload from the
    // cases — the Doctors section is the two joined on the doctor's name.
    [cases, config] = await Promise.all([api.listCases(), api.hospitalConfig()]);
  } catch {
    // Backend down: render the screens against preview data rather than a
    // row of zeroes. `demo` makes the view say so and disables every action.
    cases = DEMO_CASES;
    config = DEMO_CONFIG;
    demo = true;
  }

  return (
    <DashboardView
      initialCases={cases}
      doctors={config?.doctors ?? []}
      departments={config?.departments ?? []}
      demo={demo}
    />
  );
}
