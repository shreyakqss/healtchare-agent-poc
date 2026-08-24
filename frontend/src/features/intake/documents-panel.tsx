"use client";

import { useRef, useState } from "react";
import { casesApi } from "@/lib/api";
import type { Attachment } from "@/lib/api";
import { ATTACHMENT_KINDS } from "@/lib/constants";
import { bytes } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/form";
import { Alert, EmptyState, useToast } from "@/components/ui/feedback";
import { Icons } from "@/components/ui/icons";
import { Badge } from "@/components/ui/badge";

export function DocumentsPanel({ ensureSession }: { ensureSession: () => Promise<{ caseId: string }> }) {
  const [kind, setKind] = useState<string>(ATTACHMENT_KINDS[0].id);
  const [files, setFiles] = useState<Attachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const { caseId } = await ensureSession();
      const saved = await casesApi.upload(caseId, file, kind, "patient");
      setFiles((f) => [saved, ...f]);
      toast.push({ tone: "success", message: `${saved.filename} added to your case.` });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="space-y-5">
      <Alert tone="info" title="Shared with your clinician, never interpreted automatically">
        Reports and images you add here are stored and shown to the care team alongside your answers. They do not change anything on their own.
      </Alert>

      <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
        <Field label="Document type" htmlFor="doc-kind">
          <Select id="doc-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
            {ATTACHMENT_KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
          </Select>
        </Field>
        <div>
          <input ref={inputRef} id="doc-file" type="file" className="sr-only" accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.webp,.gif"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); }} />
          <Button type="button" loading={busy} icon={<Icons.upload size={16} />} onClick={() => inputRef.current?.click()}>Choose file</Button>
        </div>
      </div>
      <p className="-mt-2 text-xs text-fg-subtle">PDF, text or image, up to 25 MB. Synthetic documents only.</p>
      {error ? <Alert tone="danger">{error}</Alert> : null}

      {files.length ? (
        <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
          {files.map((f) => (
            <li key={f.id} className="flex items-center gap-3 px-4 py-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-sunken text-fg-muted">
                {f.mime_type.startsWith("image/") ? <Icons.image size={18} /> : <Icons.file size={18} />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{f.filename}</p>
                <p className="text-xs text-fg-muted">{ATTACHMENT_KINDS.find((k) => k.id === f.kind)?.label ?? f.kind} · {bytes(f.size_bytes)}</p>
              </div>
              <Badge tone={f.has_text ? "success" : "neutral"}>{f.has_text ? "Text extracted" : "Stored for the clinician"}</Badge>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState icon={<Icons.paperclip size={20} />} title="No documents yet" description="Add a recent lab report, prescription or referral if you have one. This is optional." />
      )}
    </div>
  );
}