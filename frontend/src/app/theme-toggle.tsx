"use client";

import { icons } from "@/lib/ui";

/**
 * Light/dark switch.
 *
 * Holds no React state: the current theme lives on `<html data-theme>`, and
 * both glyphs are rendered with CSS deciding which one shows. That keeps the
 * button correct on the server render, during hydration, and after a click,
 * without an effect or a hydration mismatch.
 */
export default function ThemeToggle() {
  function toggle() {
    const root = document.documentElement;
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    localStorage.setItem("theme", next);
  }

  return (
    <button
      onClick={toggle}
      aria-label="Toggle light and dark theme"
      title="Toggle theme"
      className="grid size-7 place-items-center rounded border border-line text-dim transition-colors hover:border-faint hover:text-text"
    >
      <icons.moon className="hidden text-[14px] dark:block" />
      <icons.sun className="text-[14px] dark:hidden" />
    </button>
  );
}
