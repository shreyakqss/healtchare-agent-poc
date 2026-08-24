"use client";

import { useState } from "react";
import { casesApi, type CaseDetail, type Fact } from "@/lib/api";
import { FIELD_LABEL } from "@/lib/constants";
import { bytes, cn } from "@/lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, Icons, SectionTitle } from "@/components/ui";

function Source({ source, turn }: { source: "patient" | "hms"; turn: number }) {
  return (
    <span className="ml-2 text-[11px] text-fg-subtle">{source === "hms" ? "hospital record" : `patient, turn ${turn + 1}`}</span>
  );
}

export function PatientRecord({ c }: { c: CaseDetail }) {
  const [showTranscript, setShowTranscript] = useState(false);
  const groups = new Map<string, Fact[]>();
  for (const f of c.facts) groups.set(f.kind, [...(groups.get(f.kind) ?? []), f]);

  return (
    <Card>
      <CardHeader title="What the patient said" description="Original statements. Your edits are kept separately and never overwrite these." />
      <CardBody className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          {[...groups.entries()].map(([kind, facts]) => (
            <div key={kind}>
              <SectionTitle>{FIELD_LABEL[kind] ?? kind}</SectionTitle>
              <ul className="mt-1.5 space-y-1 text-sm">
                {facts.map((f) => (
                  <li key={f.id} className={cn(f.confidence < 0.5 && "text-fg-muted")}>
                    {f.value}<Source source={f.source} turn={f.source_turn} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {(["allergy", "medication"] as const).map((kind) => {
            const rows = c.allergies_medications.filter((e) => e.kind === kind);
            return (
              <div key={kind}>
                <SectionTitle>{kind === "allergy" ? "Allergies" : "Medications"}</SectionTitle>
                {rows.length ? (
                  <ul className="mt-1.5 space-y-1 text-sm">
                    {rows.map((e) => (
                      <li key={e.id}>{e.name}{e.reaction_or_dose ? <span className="text-fg-muted"> ({e.reaction_or_dose})</span> : null}<Source source={e.source} turn={e.source_turn} /></li>
                    ))}
                  </ul>
                ) : <p className="mt-1.5 text-sm text-fg-subtle">None recorded</p>}
              </div>
            );
          })}
        </div>

        <div>
          <SectionTitle>Documents</SectionTitle>
          {c.attachments.length ? (
            <ul className="mt-2 divide-y divide-line rounded-md border border-line">
              {c.attachments.map((a) => (
                <li key={a.id} className="flex items-center gap-3 px-3 py-2.5 text-sm">
                  {a.mime_type.startsWith("image/") ? <Icons.image size={16} className="text-fg-subtle" /> : <Icons.file size={16} className="text-fg-subtle" />}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{a.filename}</span>
                    <span className="text-xs text-fg-muted">{a.kind.replace(/_/g, " ")} · {bytes(a.size_bytes)} · {a.has_text ? "text extracted" : "stored, not interpreted"}</span>
                  </span>
                  <a href={casesApi.fileUrl(c.case_id, a.id)} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-1 rounded-sm px-2 text-xs font-medium text-brand hover:bg-brand-soft">
                    <Icons.download size={14} /> Open
                  </a>
                </li>
              ))}
            </ul>
          ) : <p className="mt-1.5 text-sm text-fg-subtle">No documents uploaded</p>}
        </div>

        <div>
          <Button variant="ghost" size="sm" onClick={() => setShowTranscript((v) => !v)} aria-expanded={showTranscript}
            iconRight={<Icons.chevronDown size={14} className={cn("transition-transform", showTranscript && "rotate-180")} />}>
            {showTranscript ? "Hide" : "Show"} transcript ({c.transcript.length} turns)
          </Button>
          {showTranscript ? (
            <ol className="mt-2 space-y-2 rounded-md border border-line bg-sunken/60 p-3">
              {c.transcript.map((m) => (
                <li key={m.turn_index} className="text-sm">
                  <Badge tone={m.role === "patient" ? "brand" : "neutral"} className="mr-2">{m.role}</Badge>
                  <span className="text-fg">{m.content}</span>
                </li>
              ))}
            </ol>
          ) : null}
        </div>
      </CardBody>
    </Card>
  );
}