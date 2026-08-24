"use client";

import { useState } from "react";
import type { HospitalConfig } from "@/lib/api/types";
import { FIELD_LABEL } from "@/lib/constants";
import { Button, Card, CardBody, CardHeader, EmptyState, Icons, IconButton, Select } from "@/components/ui";
import type { ConfigEditor } from "@/features/admin/use-config-editor";

const KNOWN = Object.keys(FIELD_LABEL).filter((k) => k !== "condition");

export function IntakeFieldsTab({ editor }: { editor: ConfigEditor }) {
  const cfg = editor.config as HospitalConfig;
  const fields = cfg.required_intake_fields ?? [];
  const available = KNOWN.filter((k) => !fields.includes(k));
  const [pick, setPick] = useState("");
  const set = (next: string[]) => editor.update((c) => ({ ...c, required_intake_fields: next }));
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= fields.length) return;
    const next = [...fields];
    [next[i], next[j]] = [next[j], next[i]];
    set(next);
  };

  return (
    <Card className="max-w-2xl">
      <CardHeader title="Required intake fields" description="What the assistant must collect before pre-screening can run. The order here is the asking order. The complaint usually comes first, since that is what the patient opened the chat to talk about." />
      {fields.length === 0 ? <EmptyState title="No required fields" description="Intake would end immediately. Add at least one." /> : (
        <ol className="divide-y divide-line">
          {fields.map((f, i) => (
            <li key={f} className="flex items-center gap-3 px-5 py-2.5">
              <span className="tabular w-6 text-xs text-fg-subtle">{i + 1}.</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{FIELD_LABEL[f] ?? f}</p>
                <p className="font-mono text-xs text-fg-subtle">{f}</p>
              </div>
              <IconButton size="sm" label="Move up" disabled={i === 0} onClick={() => move(i, -1)} icon={<Icons.chevronDown size={14} className="rotate-180" />} />
              <IconButton size="sm" label="Move down" disabled={i === fields.length - 1} onClick={() => move(i, 1)} icon={<Icons.chevronDown size={14} />} />
              <IconButton size="sm" label={`Remove ${FIELD_LABEL[f] ?? f}`} onClick={() => set(fields.filter((x) => x !== f))} icon={<Icons.trash size={14} />} />
            </li>
          ))}
        </ol>
      )}
      <CardBody className="flex flex-wrap items-end gap-2 border-t border-line">
        <div className="min-w-56 flex-1">
          <label htmlFor="add-field" className="mb-1.5 block text-sm font-medium">Add a field</label>
          <Select id="add-field" value={pick} onChange={(e) => setPick(e.target.value)} disabled={available.length === 0}>
            <option value="">{available.length ? "Choose a field" : "All known fields are in use"}</option>
            {available.map((k) => <option key={k} value={k}>{FIELD_LABEL[k]}</option>)}
          </Select>
        </div>
        <Button variant="secondary" disabled={!pick} icon={<Icons.plus size={14} />} onClick={() => { set([...fields, pick]); setPick(""); }}>Add</Button>
      </CardBody>
    </Card>
  );
}