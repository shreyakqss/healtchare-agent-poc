"use client";

import Link from "next/link";
import { Avatar, Badge, EmptyState, Icons, PriorityBadge, StatusBadge, Table, Td, Th } from "@/components/ui";
import type { CaseListItem } from "@/lib/api/types";
import { timeAgo } from "@/lib/utils";
import { ageSex, patientName } from "@/features/clinic/derive";

export function QueueTable({ rows, total, now }: { rows: CaseListItem[]; total: number; now: number }) {
  if (total === 0) {
    return <EmptyState icon={<Icons.list size={20} />} title="No cases yet" description="Cases appear here as soon as a patient starts an intake conversation." />;
  }
  if (rows.length === 0) {
    return <EmptyState icon={<Icons.search size={20} />} title="No cases match these filters" description="Try widening the status, priority or department filter." />;
  }
  return (
    <Table>
      <thead className="sticky top-0 z-10">
        <tr>
          <Th>Patient</Th>
          <Th>Complaint</Th>
          <Th>Priority</Th>
          <Th>Status</Th>
          <Th>Department → Doctor</Th>
          <Th className="text-right">Missing</Th>
          <Th>Updated</Th>
          <Th><span className="sr-only">Open</span></Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => {
          const name = patientName(c);
          return (
            <tr key={c.case_id} className="group transition-colors hover:bg-sunken">
              <Td>
                <Link href={`/cases/${c.case_id}`} className="flex items-center gap-3 focus-visible:outline-none">
                  <Avatar name={name || "?"} size="sm" />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-fg">{name || <span className="text-fg-subtle">Unnamed patient</span>}</span>
                    <span className="flex items-center gap-1.5 text-xs text-fg-subtle">
                      {ageSex(c) || "–"}
                      {c.hms_patient_id ? <Badge tone="info" className="px-1.5 py-0 text-[10px]">{c.hms_patient_id}</Badge> : null}
                    </span>
                  </span>
                </Link>
              </Td>
              <Td className="max-w-[260px]"><span className="block truncate text-fg-muted" title={c.chief_complaint ?? undefined}>{c.chief_complaint ?? "–"}</span></Td>
              <Td><PriorityBadge priority={c.priority} /></Td>
              <Td><StatusBadge status={c.status} /></Td>
              <Td>
                {c.department_name ? (
                  <span className="text-fg">{c.department_name}<span className="text-fg-subtle"> → </span><span className="text-fg-muted">{c.doctor_name ?? "unassigned"}</span></span>
                ) : <span className="text-fg-subtle">Not routed</span>}
              </Td>
              <Td className="tabular text-right">{c.missing_count > 0 ? <Badge tone="warning">{c.missing_count}</Badge> : <span className="text-fg-subtle">0</span>}</Td>
              <Td className="whitespace-nowrap text-fg-muted" suppressHydrationWarning>{timeAgo(c.updated_at ?? c.created_at, now)}</Td>
              <Td className="w-10 pr-3">
                <Link href={`/cases/${c.case_id}`} aria-label={`Open case for ${name || "unnamed patient"}`} className="flex h-8 w-8 items-center justify-center rounded-md text-fg-subtle group-hover:text-fg">
                  <Icons.chevronRight size={16} />
                </Link>
              </Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}