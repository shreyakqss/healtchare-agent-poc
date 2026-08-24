"use client";

import { useState } from "react";
import type { Department, Doctor, HospitalConfig } from "@/lib/api";

const KEY = "careflow.doctor";

export interface Me { id: string; name: string; department_id: string; department_name: string }

export function resolveMe(id: string | null, config: HospitalConfig | null): Me | null {
  if (!id || !config) return null;
  const doc = config.doctors.find((d: Doctor) => d.id === id);
  if (!doc) return null;
  const dep = config.departments.find((d: Department) => d.id === doc.department_id);
  return { id: doc.id, name: doc.name, department_id: doc.department_id, department_name: dep?.name ?? doc.department_id };
}

function readStored(): string | null {
  try {
    return typeof window === "undefined" ? null : localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function useDoctor(config: HospitalConfig | null) {
  const [me, setMeState] = useState<Me | null>(() => resolveMe(readStored(), config));
  function setMe(id: string | null) {
    try {
      if (id) localStorage.setItem(KEY, id);
      else localStorage.removeItem(KEY);
    } catch {
      /* private mode */
    }
    setMeState(resolveMe(id, config));
  }
  return { me, setMe };
}