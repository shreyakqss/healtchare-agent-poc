"use client";

import { useState } from "react";
import { hmsApi } from "@/lib/api";
import type { HMSPatient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { Icons } from "@/components/ui/icons";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function RecordLink({ linked, onLink, locked }: { linked: HMSPatient | null; onLink: (p: HMSPatient | null) => void; locked: boolean }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<HMSPatient[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search() {
    setBusy(true);
    setError(null);
    try {
      setResults(await hmsApi.searchPatients(query));
    } catch {
      setError("Could not reach the hospital record system.");
    } finally {
      setBusy(false);
    }
  }

  if (linked) {
    return (
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge tone="brand"><Icons.link size={12} /> Linked: {linked.name} · {linked.mrn}</Badge>
        {!locked ? (
          <button type="button" onClick={() => onLink(null)} className="text-xs text-fg-muted underline-offset-2 hover:underline">Unlink</button>
        ) : null}
      </div>
    );
  }
  if (locked) return null;

  return (
    <div className="rounded-md border border-dashed border-line-strong px-3.5 py-3">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex w-full items-center justify-between gap-3 text-left">
        <span className="flex items-center gap-2 text-sm font-medium">
          <Icons.link size={16} className="text-fg-muted" /> Link my hospital record
          <span className="text-xs font-normal text-fg-muted">(optional)</span>
        </span>
        <Icons.chevronDown size={16} className={cn("text-fg-muted transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div className="mt-3 space-y-3">
          <p className="text-xs leading-5 text-fg-muted">If the clinic already knows you, we can skip re-asking your history, medications and allergies.</p>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void search(); }}>
            <label htmlFor="mrn-search" className="sr-only">Search by name or record number</label>
            <Input id="mrn-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Name or record number (e.g. MRN-10021)" />
            <Button type="submit" variant="secondary" loading={busy} icon={<Icons.search size={16} />}>Search</Button>
          </form>
          {error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}
          {results ? (
            results.length ? (
              <ul className="divide-y divide-line overflow-hidden rounded-md border border-line">
                {results.map((p) => (
                  <li key={p.mrn}>
                    <button type="button" onClick={() => { onLink(p); setOpen(false); }} className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-sm hover:bg-sunken">
                      <span><span className="font-medium">{p.name}</span><span className="ml-2 text-fg-muted">{p.age} · {p.sex}</span></span>
                      <span className="font-mono text-xs text-fg-muted">{p.mrn}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-fg-muted">No matching record. You can continue without linking.</p>
            )
          ) : null}
        </div>
      ) : null}
    </div>
  );
}