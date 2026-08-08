import { ApiError, api, type HospitalDoc, type HospitalSummary } from "@/lib/api";
import HospitalBuilder from "./hospital-builder";

// The active clinic changes at runtime — never prerendered.
export const dynamic = "force-dynamic";

export default async function HospitalPage() {
  let hospitals: HospitalSummary[] = [];
  let doc: HospitalDoc | null = null;
  let yamlText = "";
  let selected = "";
  let error: string | null = null;

  try {
    const config = await api.hospitalConfig();
    selected = config.hospital_id;
    const [list, json, yaml] = await Promise.all([
      api.listHospitals(),
      api.hospitalJson(selected),
      api.hospitalYaml(selected),
    ]);
    hospitals = list;
    doc = json.config;
    yamlText = yaml.yaml_text;
  } catch (err) {
    error = err instanceof ApiError ? err.message : String(err);
  }

  return (
    <HospitalBuilder
      initialHospitals={hospitals}
      initialDoc={doc}
      initialYaml={yamlText}
      initialSelected={selected}
      initialError={error}
    />
  );
}
