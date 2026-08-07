"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ApiError,
  PRIORITY_STYLES,
  STATUS_STYLES,
  api,
  type CaseListItem,
} from "@/lib/api";

export default function CaseTable({
  initialCases,
  initialError,
}: {
  initialCases: CaseListItem[];
  initialError: string | null;
}) {
  // Seeded from the server render, so there is no fetch-on-mount effect.
  const [cases, setCases] = useState(initialCases);
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      setCases(await api.listCases());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="mt-4 flex justify-end">
        <button
          onClick={() => void refresh()}
          disabled={busy}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          {busy ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error && (
        <p className="mt-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
          {error}
        </p>
      )}

      <div className="mt-4 overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <table className="w-full text-sm">
          <thead className="border-b border-zinc-200 text-left text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
            <tr>
              <th className="px-4 py-3 font-medium">Reason for visit</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Priority</th>
              <th className="px-4 py-3 font-medium">Department</th>
              <th className="px-4 py-3 font-medium">Doctor</th>
              <th className="px-4 py-3 font-medium">Updated</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {cases.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-zinc-500">
                  No cases yet. Run{" "}
                  <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">
                    python scripts/seed.py --reset
                  </code>{" "}
                  or start an intake.
                </td>
              </tr>
            )}
            {cases.map((item) => (
              <tr
                key={item.case_id}
                className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
              >
                <td className="px-4 py-3">
                  {item.chief_complaint ?? (
                    <span className="text-zinc-400">Not recorded</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-medium ${
                      STATUS_STYLES[item.status] ?? "bg-zinc-100 dark:bg-zinc-800"
                    }`}
                  >
                    {item.status.replaceAll("_", " ")}
                  </span>
                </td>
                <td className="px-4 py-3">
                  {item.priority ? (
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-medium ring-1 ${
                        PRIORITY_STYLES[item.priority] ?? ""
                      }`}
                    >
                      {item.priority}
                    </span>
                  ) : (
                    <span className="text-zinc-400">—</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {item.department ?? <span className="text-zinc-400">—</span>}
                </td>
                <td className="px-4 py-3">
                  {item.doctor_name ?? <span className="text-zinc-400">—</span>}
                </td>
                <td className="px-4 py-3 text-zinc-500">
                  {new Date(item.updated_at ?? item.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-3 text-right">
                  <Link
                    href={`/cases/${item.case_id}`}
                    className="font-medium underline underline-offset-2"
                  >
                    Open
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
