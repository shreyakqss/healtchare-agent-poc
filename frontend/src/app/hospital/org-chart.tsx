"use client";

import { useState } from "react";
import type { HospitalDoc } from "@/lib/api";
import { Tag, icons } from "@/lib/ui";

/**
 * Hospital → departments → doctors, drawn from the config being edited.
 *
 * Laid out with CSS and one SVG connector band rather than a graph library:
 * the shape is a fixed two-level tree, so a layout engine would be a
 * dependency earning nothing.
 */
export default function OrgChart({ doc }: { doc: HospitalDoc }) {
  const departments = doc.departments ?? [];
  const doctors = doc.doctors ?? [];
  const [selected, setSelected] = useState<string | null>(null);

  const active = selected ?? departments[0]?.id ?? null;
  const activeDoctors = doctors.filter((d) => d.department_id === active);
  const activeDepartment = departments.find((d) => d.id === active);

  return (
    <div>
      <div className="mx-auto w-fit rounded-md border border-accent/30 bg-accent/8 px-5 py-2.5 text-center">
        <p className="eyebrow">Hospital</p>
        <p className="text-sm font-semibold text-text">
          {doc.hospital?.name ?? "Unnamed clinic"}
        </p>
      </div>

      {/* connector band: one trunk down, one branch per department */}
      {departments.length > 0 && (
        <svg
          viewBox={`0 0 ${departments.length * 100} 40`}
          preserveAspectRatio="none"
          className="h-10 w-full"
          aria-hidden
        >
          <line
            x1={(departments.length * 100) / 2}
            y1="0"
            x2={(departments.length * 100) / 2}
            y2="18"
            stroke="var(--color-line)"
            strokeWidth="1.5"
          />
          <line
            x1={50}
            y1="18"
            x2={departments.length * 100 - 50}
            y2="18"
            stroke="var(--color-line)"
            strokeWidth="1.5"
          />
          {departments.map((department, index) => (
            <line
              key={department.id}
              x1={index * 100 + 50}
              y1="18"
              x2={index * 100 + 50}
              y2="40"
              stroke={
                department.id === active ? "var(--color-accent)" : "var(--color-line)"
              }
              strokeWidth="1.5"
            />
          ))}
        </svg>
      )}

      <div
        className="grid gap-2"
        style={{
          gridTemplateColumns: `repeat(${Math.max(1, departments.length)}, minmax(0, 1fr))`,
        }}
      >
        {departments.map((department) => {
          const count = doctors.filter((d) => d.department_id === department.id).length;
          const isActive = department.id === active;
          return (
            <button
              key={department.id}
              onClick={() => setSelected(department.id)}
              className={`rounded border px-2 py-2 text-center transition-colors ${
                isActive
                  ? "border-accent/50 bg-accent/8"
                  : "border-line bg-surface/60 hover:border-faint"
              }`}
            >
              <p className="truncate text-xs font-medium text-text">{department.name}</p>
              <p className="mt-0.5 text-[10px] text-faint">
                {count} {count === 1 ? "doctor" : "doctors"}
                {department.default && " · default"}
              </p>
            </button>
          );
        })}
      </div>

      {/* selected department's doctors */}
      <div className="mt-4 rounded-md border border-line bg-ink/40 p-4">
        <p className="eyebrow mb-3">
          {activeDepartment ? `${activeDepartment.name} · clinicians` : "No departments"}
        </p>
        {activeDoctors.length === 0 ? (
          <p className="text-sm text-faint">
            No doctors assigned to this department yet.
          </p>
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {activeDoctors.map((doctor) => (
              <li
                key={doctor.id}
                className="rounded border border-line bg-surface/70 px-3 py-2.5"
              >
                <p className="flex items-center gap-2 text-sm font-medium text-text">
                  <icons.stethoscope className="text-[14px] text-accent" />
                  {doctor.name}
                </p>
                <p className="mt-0.5 font-mono text-[10px] text-faint">{doctor.id}</p>
                {doctor.specialty && (
                  <p className="mt-1 text-[11px] text-dim">{doctor.specialty}</p>
                )}
                <div className="mt-2 flex flex-wrap gap-1">
                  {(doctor.working_days ?? []).map((day) => (
                    <Tag key={day} className="px-1.5 py-0 text-[10px] uppercase">
                      {day}
                    </Tag>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
