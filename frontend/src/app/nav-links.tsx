"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { icons } from "@/lib/ui";

/**
 * One tab per person who uses the platform: the patient, the doctor seeing
 * them, and the staff running the queue. Hospital configuration is an
 * administrator's setup task rather than daily work, so it sits apart from
 * these — see the settings link in the header.
 */
const LINKS = [
  { href: "/", label: "Patient Intake", Icon: icons.users },
  { href: "/doctor", label: "Doctor", Icon: icons.stethoscope },
  { href: "/dashboard", label: "Staff Dashboard", Icon: icons.grid },
];

export default function NavLinks() {
  const pathname = usePathname();

  return (
    <div className="flex items-center gap-1">
      {LINKS.map(({ href, label, Icon }) => {
        // `/cases/*` is opened from the dashboard, so keep that tab lit.
        const active =
          href === "/"
            ? pathname === "/"
            : pathname.startsWith(href) ||
              (href === "/dashboard" && pathname.startsWith("/cases"));
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`flex items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors ${
              active
                ? "bg-raised text-text shadow-[inset_0_-2px_0_0_var(--color-accent)]"
                : "text-dim hover:bg-raised/60 hover:text-text"
            }`}
          >
            <Icon className="text-[15px]" />
            {label}
          </Link>
        );
      })}
    </div>
  );
}

/**
 * Hospital configuration, kept out of the main tabs. It is administrator
 * setup — departments, doctors, triage rules — not something a patient or a
 * clinician on shift should be steered into.
 */
export function AdminLink() {
  const pathname = usePathname();
  const active = pathname.startsWith("/hospital");

  return (
    <Link
      href="/hospital"
      aria-current={active ? "page" : undefined}
      title="Hospital configuration"
      className={`flex items-center gap-2 rounded px-2.5 py-1.5 text-xs transition-colors ${
        active ? "bg-raised text-text" : "text-faint hover:bg-raised/60 hover:text-dim"
      }`}
    >
      <icons.building className="text-[14px]" />
      <span className="hidden lg:inline">Configuration</span>
    </Link>
  );
}
