import { api, type VoiceStatus } from "@/lib/api";
import PatientPortal from "./patient-portal";

// A live intake session — never prerendered.
export const dynamic = "force-dynamic";

export default async function PatientPage() {
  // The clinic name is the only config the patient surface needs; if the
  // backend is unreachable the portal still renders and reports the failure.
  let clinicName = "Your clinic";
  try {
    const config = await api.hospitalConfig();
    clinicName = config.hospital.name ?? config.hospital_id;
  } catch {
    /* portal surfaces the connection error on first action */
  }

  // Probed here so the portal knows whether to offer voice at all. Voice being
  // unavailable must never stop text intake, so this failing is not an error.
  let voice: VoiceStatus | null = null;
  try {
    voice = await api.voiceStatus();
  } catch {
    /* voice stays hidden; typing is unaffected */
  }

  return <PatientPortal clinicName={clinicName} voice={voice} />;
}
