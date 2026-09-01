"use client";

import type { Attachment } from "@/lib/api";
import { attachmentKindLabel } from "@/lib/constants";
import { bytes } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Alert, EmptyState } from "@/components/ui/feedback";
import { Icons } from "@/components/ui/icons";

export function DocumentsPanel({ attachments, pastAttachments, skippedKinds }: {
  attachments: Attachment[];
  pastAttachments: Attachment[];
  skippedKinds: Record<string, string | null>;
}) {
  const skipped = Object.entries(skippedKinds);

  return (
    <div className="space-y-6">
      <Alert tone="info" title="Shared with your clinician, never interpreted automatically">
        Documents are stored and shown to your care team. They do not change your triage on their own.
      </Alert>

      <section className="space-y-2.5" aria-label="This visit">
        <h3 className="text-sm font-semibold">This visit</h3>
        {attachments.length || skipped.length ? (
          <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
            {attachments.map((file) => (
              <li key={file.id} className="flex items-center gap-3 px-4 py-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-sunken text-fg-muted">
                  {file.mime_type.startsWith("image/") ? <Icons.image size={18} /> : <Icons.file size={18} />}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{file.filename}</p>
                  <p className="text-xs text-fg-muted">{attachmentKindLabel(file.kind)} · {bytes(file.size_bytes)}</p>
                </div>
                <Badge tone={file.has_text ? "success" : "neutral"}>
                  {file.has_text ? "Text extracted" : "Stored for the clinician"}
                </Badge>
              </li>
            ))}
            {skipped.map(([kind, reason]) => (
              <li key={kind} className="flex items-center gap-3 px-4 py-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-sunken text-fg-subtle">
                  <Icons.file size={18} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-fg-muted">{attachmentKindLabel(kind)}</p>
                  <p className="truncate text-xs text-fg-subtle">{reason ?? "Not provided"}</p>
                </div>
                <Badge tone="neutral">Skipped</Badge>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={<Icons.paperclip size={20} />}
            title="No documents yet"
            description="Attach a recent lab report, prescription or referral from the conversation."
          />
        )}
      </section>

      {pastAttachments.length ? (
        <section className="space-y-2.5" aria-label="Past visits">
          <h3 className="text-sm font-semibold">From past visits</h3>
          <p className="text-xs text-fg-muted">
            Read-only. The assistant can refer to these when answering your questions.
          </p>
          <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
            {pastAttachments.map((file) => (
              <li key={file.id} className="flex items-center gap-3 px-4 py-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-sunken text-fg-muted">
                  {file.mime_type.startsWith("image/") ? <Icons.image size={18} /> : <Icons.file size={18} />}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{file.filename}</p>
                  <p className="text-xs text-fg-muted">
                    {attachmentKindLabel(file.kind)} · {new Date(file.created_at).toLocaleDateString()}
                  </p>
                </div>
                <Badge tone="neutral">Past visit</Badge>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
