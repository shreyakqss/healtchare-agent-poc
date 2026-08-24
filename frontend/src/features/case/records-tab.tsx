"use client";

import { useState } from "react";
import { casesApi, type Attachment, type CaseDetail, type Entry, type Fact } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/feedback";
import { Table, Td, Th } from "@/components/ui/data";
import { Button } from "@/components/ui/button";
import { Icons } from "@/components/ui/icons";
import { FIELD_LABEL } from "@/lib/constants";
import { bytes, cn, formatDateTime, titleCase } from "@/lib/utils";

const SENTINELS = new Set(["None reported by patient", "Declined to answer", "Answered - see the intake transcript"]);

function Source({ source, turn }: { source: "patient" | "hms"; turn: number }) {
  return source === "hms"
    ? <Badge tone="info"><Icons.database size={11} /> Hospital record</Badge>
    : <span className="text-xs text-fg-muted">Patient · turn {turn}</span>;
}

function Value({ v }: { v: string }) {
  return SENTINELS.has(v) ? <span className="italic text-fg-subtle">{v}</span> : <>{v}</>;
}

function groupFacts(facts: Fact[]): Array<[string, Fact[]]> {
  const order = Object.keys(FIELD_LABEL);
  const map = new Map<string, Fact[]>();
  for (const f of facts) map.set(f.kind, [...(map.get(f.kind) ?? []), f]);
  return [...map.entries()].sort((a, b) => {
    const ia = order.indexOf(a[0]);
    const ib = order.indexOf(b[0]);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
}

function AttachmentRow({ a, caseId }: { a: Attachment; caseId: string }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-md border border-line p-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-fg-muted">{a.has_text ? <Icons.file size={16} /> : <Icons.image size={16} />}</span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{a.filename}</span>
        <Badge>{titleCase(a.kind)}</Badge>
        <span className="tabular text-xs text-fg-subtle">{bytes(a.size_bytes)}</span>
        <span className="text-xs text-fg-subtle">by {a.uploaded_by}</span>
        <Badge tone={a.has_text ? "success" : "neutral"}>{a.has_text ? "Text extracted" : "Stored only"}</Badge>
        <a href={casesApi.fileUrl(caseId, a.id)} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-1 rounded-sm px-2 text-xs font-medium text-brand hover:bg-brand-soft">
          <Icons.download size={14} /> Download
        </a>
        {a.extracted_text ? (
          <Button variant="ghost" size="sm" onClick={() => setOpen((o) => !o)} iconRight={<Icons.chevronDown size={14} className={cn("transition-transform", open && "rotate-180")} />}>
            {open ? "Hide text" : "Preview text"}
          </Button>
        ) : null}
      </div>
      <p className="mt-1 text-[11px] text-fg-subtle" suppressHydrationWarning>Uploaded {formatDateTime(a.created_at)} · displayed to the clinician, never interpreted automatically</p>
      {open && a.extracted_text ? (
        <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-sunken p-3 font-mono text-xs leading-5 text-fg">{a.extracted_text}</pre>
      ) : null}
    </li>
  );
}

export function RecordsTab({ detail }: { detail: CaseDetail }) {
  const groups = groupFacts(detail.facts);
  const entries: Entry[] = detail.allergies_medications;

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader title="Patient-reported facts" description="Original statements are never overwritten; clinician corrections live on the review." />
        <CardBody className="p-0">
          {!detail.facts.length ? (
            <EmptyState title="No facts recorded" />
          ) : (
            <Table>
              <thead><tr><Th className="w-44">Kind</Th><Th>Value</Th><Th className="w-44">Source</Th><Th className="w-24 text-right">Confidence</Th></tr></thead>
              <tbody>
                {groups.map(([kind, facts]) =>
                  facts.map((f, i) => (
                    <tr key={f.id}>
                      <Td className="text-sm text-fg-muted">{i === 0 ? (FIELD_LABEL[kind] ?? titleCase(kind)) : <span className="sr-only">{FIELD_LABEL[kind] ?? titleCase(kind)}</span>}</Td>
                      <Td className="text-sm"><Value v={f.value} /></Td>
                      <Td><Source source={f.source} turn={f.source_turn} /></Td>
                      <Td className="tabular text-right text-xs text-fg-muted">{Math.round(f.confidence * 100)}%</Td>
                    </tr>
                  )),
                )}
              </tbody>
            </Table>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Allergies & medications" />
        <CardBody className="p-0">
          {!entries.length ? (
            <EmptyState title="None recorded" />
          ) : (
            <Table>
              <thead><tr><Th className="w-32">Type</Th><Th>Name</Th><Th>Reaction / dose</Th><Th className="w-44">Source</Th></tr></thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id}>
                    <Td><Badge tone={e.kind === "allergy" ? "danger" : "neutral"}>{titleCase(e.kind)}</Badge></Td>
                    <Td className="text-sm"><Value v={e.name} /></Td>
                    <Td className="text-sm text-fg-muted">{e.reaction_or_dose ?? "–"}</Td>
                    <Td><Source source={e.source} turn={e.source_turn} /></Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Uploaded documents" description="Stored and displayed only. Nothing here can change a priority." />
        <CardBody>
          {!detail.attachments.length ? (
            <EmptyState icon={<Icons.paperclip size={20} />} title="No documents uploaded" />
          ) : (
            <ul className="space-y-2">{detail.attachments.map((a) => <AttachmentRow key={a.id} a={a} caseId={detail.case_id} />)}</ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}