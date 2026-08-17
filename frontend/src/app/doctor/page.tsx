import { api, type CaseListItem, type HospitalConfig } from "@/lib/api";
import { DEMO_CASES, DEMO_CONFIG } from "@/lib/demo";
import DoctorView from "./doctor-view";

// A live clinical worklist — never prerendered.
export const dynamic = "force-dynamic";

export default async function DoctorPage() {
  // Fetched server-side and handed down as `initial*` props: the React
  // Compiler's `set-state-in-effect` rule fails the build on fetch-on-mount,
  // so client components here refetch only in event handlers.
  let cases: CaseListItem[] = [];
  let config: HospitalConfig | null = null;
  let demo = false;

  try {
    [cases, config] = await Promise.all([api.listCases(), api.hospitalConfig()]);
  } catch {
    // Backend down: show the worklist against preview patients so the screen
    // can be read. `demo` disables approving, prescribing and releasing.
    cases = DEMO_CASES;
    config = DEMO_CONFIG;
    demo = true;
  }

  return (
    <DoctorView
      initialCases={cases}
      doctors={config?.doctors ?? []}
      departments={config?.departments ?? []}
      demo={demo}
    />
  );
}
