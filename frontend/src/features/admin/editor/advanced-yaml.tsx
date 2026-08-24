"use client";

import { useState } from "react";
import { hospitalApi } from "@/lib/api";
import { Alert, Button, Card, CardBody, CardHeader, Icons, Textarea, useToast } from "@/components/ui";

export function AdvancedYamlTab({ hospitalId, onSaved }: { hospitalId: string; onSaved: () => Promise<void> }) {
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  async function load() {
    setLoading(true); setError(null);
    try { setText((await hospitalApi.getYaml(hospitalId)).yaml); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load the file."); }
    finally { setLoading(false); }
  }
  async function save() {
    if (text === null) return;
    setSaving(true); setError(null);
    try { await hospitalApi.saveYaml(hospitalId, text); toast.push({ tone: "success", message: "YAML saved and rules re-synced." }); await onSaved(); }
    catch (e) { setError(e instanceof Error ? e.message : "Save failed."); }
    finally { setSaving(false); }
  }

  return (
    <Card>
      <CardHeader title="Raw configuration" description="The file as it is on disk. Saving from the visual builder round-trips through a parser and drops comments; edit here to keep them."
        action={<Button size="sm" variant="secondary" icon={<Icons.refresh size={14} />} loading={loading} onClick={load}>{text === null ? "Load file" : "Reload"}</Button>} />
      <CardBody className="space-y-3">
        {error ? <Alert tone="danger" title="Rejected">{error}</Alert> : null}
        {text === null ? (
          <p className="text-sm text-fg-muted">Load the file to view or edit it. Unsaved changes in the builder are not reflected here.</p>
        ) : (
          <>
            <Textarea aria-label="Hospital YAML" value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} className="min-h-[480px] font-mono text-xs leading-5" />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={load} disabled={saving}>Discard edits</Button>
              <Button onClick={save} loading={saving}>Save YAML</Button>
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );
}