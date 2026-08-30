"use client";

import { cn } from "@/lib/utils";
import type { Department, Doctor, HospitalConfig } from "@/lib/api/types";
import { Button, Card, CardHeader, EmptyState, Icons, IconButton, Input, Select, Table, Td, Th } from "@/components/ui";
import { WEEKDAYS, slugify, type ConfigEditor } from "@/features/admin/use-config-editor";

export function DepartmentsTab({ editor }: { editor: ConfigEditor }) {
  const cfg = editor.config as HospitalConfig;
  const deps = cfg.departments ?? [];
  const docs = cfg.doctors ?? [];

  const setDeps = (next: Department[]) => editor.update((c) => ({ ...c, departments: next }));
  const setDocs = (next: Doctor[]) => editor.update((c) => ({ ...c, doctors: next }));
  const editDep = (i: number, patch: Partial<Department>) => setDeps(deps.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  const editDoc = (i: number, patch: Partial<Doctor>) => setDocs(docs.map((d, j) => (j === i ? { ...d, ...patch } : d)));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title="Departments" description="Where cases are routed. The default department receives anything no keyword matches."
          action={<Button size="sm" variant="secondary" icon={<Icons.plus size={14} />}
            onClick={() => setDeps([...deps, { id: `department_${deps.length + 1}`, name: "", default: deps.length === 0 }])}>Add department</Button>} />
        {deps.length === 0 ? <EmptyState title="No departments yet" description="Add at least one so cases have somewhere to go." /> : (
          <Table regionLabel="Departments">
            <thead><tr><Th>Id</Th><Th>Name</Th><Th className="w-28">Default</Th><Th className="w-16"><span className="sr-only">Actions</span></Th></tr></thead>
            <tbody>
              {deps.map((d, i) => (
                <tr key={i}>
                  <Td><Input aria-label="Department id" value={d.id} className="h-9 font-mono text-xs" onChange={(e) => editDep(i, { id: slugify(e.target.value) })} /></Td>
                  <Td><Input aria-label="Department name" value={d.name} className="h-9" onChange={(e) => editDep(i, { name: e.target.value })}
                    onBlur={() => { if (!d.id && d.name) editDep(i, { id: slugify(d.name) }); }} /></Td>
                  <Td>
                    <label className="flex cursor-pointer items-center gap-2 text-sm">
                      <input type="radio" name="default-department" checked={!!d.default} onChange={() => setDeps(deps.map((x, j) => ({ ...x, default: j === i })))} className="accent-brand" />
                      {d.default ? "Default" : ""}
                    </label>
                  </Td>
                  <Td><IconButton size="sm" label="Remove department" icon={<Icons.trash size={14} />} onClick={() => setDeps(deps.filter((_, j) => j !== i))} /></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Card>
        <CardHeader title="Doctors (static overrides)"
          description="Only for a department the hospital system has no live practitioner for. Live doctors come from the HMS automatically - see Practitioners count above - and never need adding here. Working days generate available slots."
          action={<Button size="sm" variant="secondary" icon={<Icons.plus size={14} />} disabled={deps.length === 0}
            onClick={() => setDocs([...docs, { id: `dr_${docs.length + 1}`, name: "", department_id: deps[0]?.id ?? "", working_days: ["mon", "tue", "wed", "thu", "fri"] }])}>Add doctor</Button>} />
        {docs.length === 0 ? <EmptyState title="No static overrides" description="Every department already has a live doctor from the hospital system." /> : (
          <Table regionLabel="Doctors">
            <thead><tr><Th>Id</Th><Th>Name</Th><Th>Department</Th><Th>Working days</Th><Th className="w-16"><span className="sr-only">Actions</span></Th></tr></thead>
            <tbody>
              {docs.map((d, i) => (
                <tr key={i}>
                  <Td><Input aria-label="Doctor id" value={d.id} className="h-9 w-32 font-mono text-xs" onChange={(e) => editDoc(i, { id: slugify(e.target.value) })} /></Td>
                  <Td><Input aria-label="Doctor name" value={d.name} className="h-9 min-w-40" placeholder="Dr. A. Mehta" onChange={(e) => editDoc(i, { name: e.target.value })} /></Td>
                  <Td>
                    <Select aria-label="Department" value={d.department_id} className="h-9 min-w-40" onChange={(e) => editDoc(i, { department_id: e.target.value })}>
                      {deps.map((x) => <option key={x.id} value={x.id}>{x.name || x.id}</option>)}
                    </Select>
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1" role="group" aria-label="Working days">
                      {WEEKDAYS.map((day) => {
                        const on = (d.working_days ?? []).includes(day);
                        return (
                          <button key={day} type="button" aria-pressed={on}
                            onClick={() => editDoc(i, { working_days: on ? (d.working_days ?? []).filter((x) => x !== day) : [...(d.working_days ?? []), day] })}
                            className={cn("h-7 w-9 rounded-sm text-[11px] font-medium uppercase transition-colors", on ? "bg-brand text-brand-fg" : "bg-sunken text-fg-muted hover:text-fg")}>
                            {day}
                          </button>
                        );
                      })}
                    </div>
                  </Td>
                  <Td><IconButton size="sm" label="Remove doctor" icon={<Icons.trash size={14} />} onClick={() => setDocs(docs.filter((_, j) => j !== i))} /></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
