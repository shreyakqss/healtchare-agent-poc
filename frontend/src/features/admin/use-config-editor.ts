"use client";

import { useCallback, useState } from "react";
import type { HospitalConfig } from "@/lib/api/types";

export interface ConfigEditor {
  config: HospitalConfig | null;
  original: HospitalConfig | null;
  dirty: boolean;
  update: (fn: (cfg: HospitalConfig) => HospitalConfig) => void;
  load: (cfg: HospitalConfig | null) => void;
  discard: () => void;
  markSaved: () => void;
}

/** Immutable config state with dirty tracking. Every updater returns a new object. */
export function useConfigEditor(initial: HospitalConfig | null): ConfigEditor {
  const [original, setOriginal] = useState<HospitalConfig | null>(initial);
  const [config, setConfig] = useState<HospitalConfig | null>(initial);

  const update = useCallback((fn: (cfg: HospitalConfig) => HospitalConfig) => {
    setConfig((c) => (c ? fn(c) : c));
  }, []);
  const load = useCallback((cfg: HospitalConfig | null) => { setOriginal(cfg); setConfig(cfg); }, []);
  const discard = useCallback(() => setConfig(original), [original]);
  const markSaved = useCallback(() => setOriginal(config), [config]);

  const dirty = JSON.stringify(config) !== JSON.stringify(original);
  return { config, original, dirty, update, load, discard, markSaved };
}

export const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

export function slugify(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}