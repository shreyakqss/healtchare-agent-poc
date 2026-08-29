import Link from "next/link";
import { Logo } from "@/components/layout/app-shell";

export const metadata = { title: "Sign-in problem" };

export default function AuthErrorPage() {
  return (
    <main id="main" className="mx-auto flex min-h-dvh max-w-lg flex-col justify-center px-6">
      <div className="mb-5 flex items-center gap-2.5"><Logo /><span className="font-semibold">CareFlow</span></div>
      <section className="rounded-lg border border-line bg-surface p-6 shadow-card">
        <h1 className="text-xl font-semibold">Sign-in could not be completed</h1>
        <p className="mt-2 text-sm leading-6 text-fg-muted">
          The login may have expired or the identity service may be unavailable. No clinical information was changed.
        </p>
        <Link href="/" className="mt-5 inline-flex rounded-md bg-brand px-3 py-2 text-sm font-medium text-brand-fg">
          Return to CareFlow
        </Link>
      </section>
    </main>
  );
}
