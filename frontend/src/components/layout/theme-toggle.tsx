"use client";

import { useState } from "react";
import { IconButton } from "@/components/ui/button";
import { Icons } from "@/components/ui/icons";

export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">(() =>
    typeof document !== "undefined" && document.documentElement.dataset.theme === "dark" ? "dark" : "light",
  );
  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch { /* private mode */ }
    setTheme(next);
  }
  return (
    <IconButton label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} onClick={toggle}
      icon={theme === "dark" ? <Icons.sun size={18} /> : <Icons.moon size={18} />} />
  );
}