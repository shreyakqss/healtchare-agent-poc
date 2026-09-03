"use client";

import { useState, type ReactNode } from "react";
import { casesApi, type Attachment, type CaseDetail, type Entry, type Fact } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/feedback";
import { Table, Td, Th } from "@/components/ui/data";
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

/** A card whose body starts collapsed - used for the sections a clinician opens on demand
 * rather than reads first, so the documents that matter most stay above the fold. */
function CollapsibleCard({ title, description, count, children }: {
  title: string; description?: string; count: number; children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left hover:bg-sunken"
      >
        <span>
          <span className="block text-[15px] font-semibold">{title}</span>
          {description ? <span className="mt-0.5 block text-sm text-fg-muted">{description}</span> : null}
        </span>
        <span className="flex shrink-0 items-center gap-2 text-fg-subtle">
          <Badge>{count}</Badge>
          <Icons.chevronDown size={16} className={cn("transition-transform", open && "rotate-180")} />
        </span>
      </button>
      {open ? <CardBody className={count ? "p-0 pt-0" : undefined}>{children}</CardBody> : null}
    </Card>
  );
}

/** Opens in a new tab, never a download - the backend serves every attachment with
 * Content-Disposition: inline. Not an <iframe>: this app's CSP sets object-src 'none' (a
 * deliberate hardening default), which blocks Chrome's built-in PDF viewer when framed. */
function AttachmentRow({ a, caseId }: { a: Attachment; caseId: string }) {
  const [showText, setShowText] = useState(false);
  const url = casesApi.fileUrl(caseId, a.id);
  return (
    <li className="rounded-md border border-line p-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-fg-muted">{a.has_text ? <Icons.file size={16} /> : <Icons.image size={16} />}</span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{a.filename}</span>
        <Badge>{titleCase(a.kind)}</Badge>
        <span className="tabular text-xs text-fg-subtle">{bytes(a.size_bytes)}</span>
        {a.has_text ? (
          <button
            type="button"
            onClick={() => setShowText((v) => !v)}
            className="inline-flex h-8 items-center gap-1.5 rounded-sm px-3 text-[13px] font-medium text-fg-muted hover:bg-sunken hover:text-fg"
          >
            <Icons.chevronDown size={14} className={cn("transition-transform", showText && "rotate-180")} /> Preview text
          </button>
        ) : null}
        <a
          href={url} target="_blank" rel="noreferrer"
          className="inline-flex h-8 items-center gap-1.5 rounded-sm px-3 text-[13px] font-medium text-fg-muted hover:bg-sunken hover:text-fg"
        >
          <Icons.external size={14} /> Open
        </a>
      </div>
      <p className="mt-1 text-[11px] text-fg-subtle" suppressHydrationWarning>Uploaded {formatDateTime(a.created_at)} by {a.uploaded_by}</p>
      {showText && a.extracted_text ? (
        <pre className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap rounded-md bg-sunken p-2.5 text-xs text-fg-muted">{a.extracted_text}</pre>
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
        <CardHeader title="Uploaded documents" description="Stored and displayed only. Nothing here can change a priority. Opens in the browser's own viewer - no download." />
        <CardBody>
          {!detail.attachments.length ? (
            <EmptyState icon={<Icons.paperclip size={20} />} title="No documents uploaded" />
          ) : (
            <ul className="space-y-2">{detail.attachments.map((a) => <AttachmentRow key={a.id} a={a} caseId={detail.case_id} />)}</ul>
          )}
        </CardBody>
      </Card>

      <CollapsibleCard title="Allergies & medications" count={entries.length}>
        {!entries.length ? (
          <EmptyState title="None recorded" />
        ) : (
          <Table regionLabel="Allergies and medications">
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
      </CollapsibleCard>

      <CollapsibleCard title="Patient-reported facts" description="Original statements are never overwritten; clinician corrections live on the review." count={detail.facts.length}>
        {!detail.facts.length ? (
          <EmptyState title="No facts recorded" />
        ) : (
          <Table regionLabel="Patient-reported facts">
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
      </CollapsibleCard>
    </div>
  );
}
