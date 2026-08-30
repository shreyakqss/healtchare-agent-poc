import Link from "next/link";
import { currentUser } from "@/lib/auth";
import { serverApi } from "@/lib/api/server";
import { Logo } from "@/components/layout/app-shell";
import { Icons } from "@/components/ui/icons";
import { Badge } from "@/components/ui/badge";
import { RoleCards } from "@/features/home/role-cards";

const ROLES = [
  { role: "patient" as const, href: "/patient", title: "Patient" },
  { role: "clinician" as const, href: "/doctor", title: "Clinician" },
  { role: "admin" as const, href: "/admin", title: "Administrator" },
];

export default async function HomePage() {
  const [user, health] = await Promise.all([
    currentUser(),
    serverApi.health().catch(() => null),
  ]);
  const roles = user ? ROLES.filter((entry) => user.roles.includes(entry.role)) : ROLES;

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex h-14 items-center justify-between px-6">
        <div className="flex items-center gap-2.5">
          <Logo />
          <span className="text-[15px] font-semibold tracking-tight">CareFlow</span>
        </div>
        <div className="flex items-center gap-3">
          {user?.roles.includes("admin") ? <Link href="/admin" className="text-sm text-fg-muted hover:text-fg">Configuration</Link> : null}
          {user ? (
            <form action="/api/auth/logout" method="post">
              <button type="submit" className="text-sm text-fg-muted hover:text-fg">Sign out</button>
            </form>
          ) : null}
        </div>
      </header>

      <main id="main" className="mx-auto flex w-full max-w-5xl flex-1 flex-col justify-center px-6 pb-16 pt-8">
        <h1 className="text-2xl font-semibold tracking-tight">Sign in to CareFlow</h1>
        <p className="mt-1 text-sm text-fg-muted">Synthetic clinic demo. A clinician reviews everything before any decision is made.</p>

        <RoleCards roles={roles} signedIn={!!user} />

        <div className="mt-10 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-fg-subtle">
          <span className="flex items-center gap-1.5"><Icons.shield size={14} /> Synthetic data only, no real patient information</span>
          <Badge tone={health ? "success" : "danger"}>{health ? "Service online" : "Service offline"}</Badge>
          {user ? <span>Signed in as <span className="text-fg-muted">{user.username ?? "CareFlow user"}</span></span> : null}
        </div>
      </main>
    </div>
  );
}
