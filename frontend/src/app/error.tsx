"use client";

import { Button } from "@/components/ui/button";

export default function ErrorPage({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <main id="main" className="mx-auto flex min-h-dvh max-w-lg items-center px-6 py-16">
      <div className="w-full rounded-lg border border-line bg-surface p-6 shadow-card" role="alert">
        <h1 className="text-lg font-semibold">This page could not be loaded</h1>
        <p className="mt-2 text-sm leading-6 text-fg-muted">
          Your changes were not submitted. Check your connection, then try again.
        </p>
        <Button className="mt-5" onClick={() => retry()}>Try again</Button>
      </div>
    </main>
  );
}
