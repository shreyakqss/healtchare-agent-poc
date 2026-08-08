import {
  buildPipeline,
  streamMetrics,
  timeline,
  voiceMetrics,
  type StreamMetrics,
  type VoiceMetrics,
} from "@/lib/agents";
import { ApiError, api, type AuditEvent } from "@/lib/api";
import OpsView, { type OpsCase } from "./ops-view";

// Live runtime state — never prerendered.
export const dynamic = "force-dynamic";

export default async function OpsPage() {
  let cases: OpsCase[] = [];
  let voice: VoiceMetrics = voiceMetrics([]);
  let stream: StreamMetrics = streamMetrics([]);
  let error: string | null = null;

  try {
    const list = await api.listCases();
    // One detail + audit fetch per case. Fine at POC scale (a handful of
    // cases); if this ever needs to serve a real queue, add a batched
    // endpoint rather than widening this fan-out.
    const loaded = await Promise.all(
      list.map(async (item) => {
        const [detail, audit] = await Promise.all([
          api.getCase(item.case_id),
          api.audit(item.case_id),
        ]);
        return { item, audit, runs: buildPipeline(detail, audit), trace: timeline(audit) };
      }),
    );
    cases = loaded.map(({ item, runs, trace }) => ({ item, runs, trace }));
    // Voice and streaming telemetry span cases, so both are rolled up from
    // every audit trail rather than read off the selected one.
    const audits = loaded.flatMap((entry) => entry.audit as AuditEvent[]);
    voice = voiceMetrics(audits);
    stream = streamMetrics(audits);
  } catch (err) {
    error = err instanceof ApiError ? err.message : String(err);
  }

  return <OpsView cases={cases} voice={voice} stream={stream} error={error} />;
}
