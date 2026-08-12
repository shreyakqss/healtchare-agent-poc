"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { icons } from "@/lib/ui";

const LINKS = [
  { href: "/ops", label: "AI Operations", Icon: icons.pulse },
  { href: "/simulation", label: "Simulation", Icon: icons.play },
  { href: "/", label: "Patients", Icon: icons.users },
  { href: "/dashboard", label: "Staff Dashboard", Icon: icons.grid },
  { href: "/hospital", label: "Hospital Builder", Icon: icons.building },
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
