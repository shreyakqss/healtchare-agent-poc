"use client";

import { Button, Icons, Input, Select } from "@/components/ui";
import { PRIORITY_LABEL, STATUS_LABEL, STATUS_ORDER } from "@/lib/constants";
import type { CaseStatus, Department, Priority } from "@/lib/api/types";
import { EMPTY_FILTERS, type QueueFilters } from "@/features/clinic/derive";

export function QueueFilters({ value, onChange, departments }: { value: QueueFilters; onChange: (f: QueueFilters) => void; departments: Department[] }) {
  const set = (patch: Partial<QueueFilters>) => onChange({ ...value, ...patch });
  const dirty = value !== EMPTY_FILTERS && (value.search || value.status || value.priority || value.department);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-[200px] flex-1">
        <Icons.search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-subtle" />
        <Input aria-label="Search patients" placeholder="Search name, complaint or MRN" value={value.search} onChange={(e) => set({ search: e.target.value })} className="pl-9" />
      </div>
      <div className="w-44"><Select aria-label="Status" value={value.status} onChange={(e) => set({ status: e.target.value as CaseStatus | "" })}>
        <option value="">All statuses</option>
        {STATUS_ORDER.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
      </Select></div>
      <div className="w-36"><Select aria-label="Priority" value={value.priority} onChange={(e) => set({ priority: e.target.value as Priority | "" })}>
        <option value="">All priorities</option>
        {(["high", "medium", "low"] as Priority[]).map((p) => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
      </Select></div>
      <div className="w-44"><Select aria-label="Department" value={value.department} onChange={(e) => set({ department: e.target.value })}>
        <option value="">All departments</option>
        {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
      </Select></div>
      {dirty ? <Button variant="ghost" size="sm" onClick={() => onChange(EMPTY_FILTERS)} icon={<Icons.x size={14} />}>Clear</Button> : null}
    </div>
  );
}