"use client";

import { IconButton } from "@/components/ui/button";
import { Icons } from "@/components/ui/icons";

export function ThemeToggle() {
  // No React state for which icon shows - a blocking inline script in app/layout.tsx stamps
  // the real theme onto <html> before first paint, so both icons are always in the DOM and
  // CSS (the same `dark:` variant used everywhere else) picks the right one. That keeps the
  // server and client markup identical (no hydration mismatch) without an effect+setState
  // render cascade just to sync one icon.
  function toggle() {
    const current = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch { /* private mode */ }
  }
  return (
    <IconButton label="Toggle theme" onClick={toggle}
      icon={
        <span className="relative inline-block h-[18px] w-[18px]">
          <Icons.moon size={18} className="absolute inset-0 dark:hidden" />
          <Icons.sun size={18} className="absolute inset-0 hidden dark:block" />
        </span>
      } />
  );
}