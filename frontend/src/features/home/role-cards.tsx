"use client";

import { useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Icons } from "@/components/ui/icons";

const LAST_ROLE_KEY = "careflow_last_role";

export interface RoleCard {
  role: "patient" | "clinician" | "admin";
  href: string;
  title: string;
}

const ROLE_ICON = {
  patient: Icons.user,
  clinician: Icons.stethoscope,
  admin: Icons.settings,
} as const;

const noSubscribe = () => () => {};

function readLastRole(): string | null {
  try {
    return localStorage.getItem(LAST_ROLE_KEY);
  } catch {
    return null; /* private browsing or storage blocked - no highlight, still fully usable */
  }
}

function loginHref(returnTo: string) {
  return `/api/auth/login?return_to=${encodeURIComponent(returnTo)}`;
}

/** Per-browser convenience only - highlights whichever role was opened last time, so a
 * returning visitor doesn't have to re-read all three cards. Never auto-navigates: the
 * picker still shows every role you're allowed, so a shared machine can't silently sign
 * in as the wrong person. */
export function RoleCards({ roles, signedIn }: { roles: RoleCard[]; signedIn: boolean }) {
  const router = useRouter();
  // null on the server and before hydration, so the first client render matches the HTML.
  const lastRole = useSyncExternalStore(noSubscribe, readLastRole, () => null);
  const [registering, setRegistering] = useState(false);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [newAccount, setNewAccount] = useState<{ username: string; password: string } | null>(null);

  function remember(role: string) {
    try {
      localStorage.setItem(LAST_ROLE_KEY, role);
    } catch {
      /* best-effort only */
    }
  }

  async function startNewPatient() {
    setRegistering(true);
    setRegisterError(null);
    try {
      const res = await fetch("/api/auth/self-register", { method: "POST" });
      if (!res.ok) throw new Error("self-register failed");
      const body = (await res.json()) as { username: string; password: string; return_to: string };
      remember("patient");
      setNewAccount({ username: body.username, password: body.password });
    } catch {
      setRegisterError("Could not create an account right now. Please try again.");
    } finally {
      setRegistering(false);
    }
  }

  return (
    <div className="mt-6 space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        {roles.map((r) => {
          const isLast = lastRole === r.role;
          const RoleIcon = ROLE_ICON[r.role];
          const cardClass = `rounded-lg border px-4 py-3.5 shadow-card transition-colors ${
            isLast ? "border-brand-ring bg-brand-soft" : "border-line bg-surface"
          }`;

          if (r.role === "patient" && !signedIn) {
            return (
              <div key={r.href} className={cardClass}>
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-brand-soft text-brand">
                    <RoleIcon size={18} />
                  </div>
                  <span className="flex-1 text-sm font-semibold">{r.title}</span>
                  {isLast ? <span className="text-[11px] font-medium text-brand">Last used</span> : null}
                </div>
                <div className="mt-3 flex gap-2">
                  {/* A plain link, not <Link>: the login route redirects off-site to Keycloak,
                      which a client-side RSC fetch cannot follow. */}
                  <a
                    href={loginHref(r.href)}
                    onClick={() => remember("patient")}
                    className="flex-1 rounded-md border border-line px-3 py-1.5 text-center text-xs font-medium hover:border-brand-ring"
                  >
                    Returning patient
                  </a>
                  <button
                    type="button"
                    onClick={() => void startNewPatient()}
                    disabled={registering}
                    className="flex-1 rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-brand-fg disabled:opacity-60"
                  >
                    {registering ? "Creating account..." : "New patient"}
                  </button>
                </div>
                {registerError ? <p className="mt-2 text-[11px] text-danger">{registerError}</p> : null}
              </div>
            );
          }

          const linkClass = `group flex items-center gap-3 hover:border-brand-ring ${cardClass}`;
          const content = (
            <>
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-brand-soft text-brand">
                <RoleIcon size={18} />
              </div>
              <span className="flex-1 text-sm font-semibold">{r.title}</span>
              {isLast ? <span className="text-[11px] font-medium text-brand">Last used</span> : null}
              <Icons.arrowRight size={16} className="shrink-0 text-fg-subtle transition-transform group-hover:translate-x-0.5" />
            </>
          );
          return signedIn ? (
            <Link key={r.href} href={r.href} onClick={() => remember(r.role)} className={linkClass}>
              {content}
            </Link>
          ) : (
            <a key={r.href} href={loginHref(r.href)} onClick={() => remember(r.role)} className={linkClass}>
              {content}
            </a>
          );
        })}
      </div>

      {newAccount ? (
        <div role="alertdialog" className="rounded-lg border border-brand-ring bg-brand-soft p-4 text-sm">
          <p className="font-semibold">Your account is ready</p>
          <p className="mt-1 text-fg-muted">Save these to sign in next time - you will not see this again:</p>
          <p className="mt-2 font-mono text-sm">
            Username: {newAccount.username}
            <br />
            Password: {newAccount.password}
          </p>
          <button
            type="button"
            onClick={() => router.push("/patient")}
            className="mt-3 rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-brand-fg"
          >
            Continue to intake form
          </button>
        </div>
      ) : null}
    </div>
  );
}
