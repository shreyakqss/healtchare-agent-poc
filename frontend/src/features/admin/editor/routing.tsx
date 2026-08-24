"use client";

import type { HospitalConfig } from "@/lib/api/types";
import { Alert, Badge, Card, CardBody, CardHeader } from "@/components/ui";
import { ChipInput } from "@/features/admin/chip-input";
import type { ConfigEditor } from "@/features/admin/use-config-editor";

export function RoutingTab({ editor }: { editor: ConfigEditor }) {
  const cfg = editor.config as HospitalConfig;
  const deps = cfg.departments ?? [];
  const map = cfg.specialty_map ?? {};
  const defaultDep = deps.find((d) => d.default);

  return (
    <div className="space-y-4">
      <Alert tone="info" title="How routing works">
        Keywords are matched against what the patient reported (reason for visit, symptoms, history). Departments are checked in the order listed
        and the first match wins. A triage rule with a specialty hint overrides this. Unmatched cases go to the default department
        {defaultDep ? <> (<span className="font-medium">{defaultDep.name}</span>)</> : null}.
      </Alert>
      <Card>
        <CardHeader title="Specialty keywords" description="Plain words or short phrases, matched case-insensitively." />
        <CardBody className="divide-y divide-line p-0">
          {deps.map((d) => (
            <div key={d.id} className="grid gap-3 px-5 py-4 sm:grid-cols-[220px_1fr]">
              <div>
                <p className="text-sm font-medium">{d.name || d.id}</p>
                <p className="font-mono text-xs text-fg-subtle">{d.id}</p>
                {d.default ? <Badge className="mt-1">Default</Badge> : null}
              </div>
              <ChipInput label={`Keywords for ${d.name || d.id}`} value={map[d.id] ?? []} placeholder={d.default ? "Optional. The default department receives unmatched cases." : "e.g. chest pain, palpitations"}
                onChange={(next) => editor.update((c) => {
                  const m = { ...(c.specialty_map ?? {}) };
                  if (next.length) m[d.id] = next; else delete m[d.id];
                  return { ...c, specialty_map: m };
                })} />
            </div>
          ))}
          {deps.length === 0 ? <p className="px-5 py-6 text-sm text-fg-muted">Add departments first.</p> : null}
        </CardBody>
      </Card>
    </div>
  );
}