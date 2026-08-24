"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Icons } from "@/components/ui/icons";

/* ---------- Skeleton / Empty / Alert ---------- */

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse-soft rounded-md bg-sunken", className)} aria-hidden="true" />;
}

export function EmptyState({ icon, title, description, action, className }: {
  icon?: ReactNode; title: string; description?: ReactNode; action?: ReactNode; className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      {icon ? <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-sunken text-fg-subtle">{icon}</div> : null}
      <p className="text-sm font-medium text-fg">{title}</p>
      {description ? <p className="mt-1 max-w-sm text-sm text-fg-muted">{description}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function Alert({ tone = "info", title, children, className }: {
  tone?: "info" | "warning" | "danger" | "success"; title?: ReactNode; children?: ReactNode; className?: string;
}) {
  const map = {
    info: { box: "bg-info-soft text-info", Icon: Icons.info },
    warning: { box: "bg-warning-soft text-warning", Icon: Icons.alert },
    danger: { box: "bg-danger-soft text-danger", Icon: Icons.alert },
    success: { box: "bg-success-soft text-success", Icon: Icons.checkCircle },
  }[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("flex gap-3 rounded-md px-3.5 py-3 text-sm", map.box, className)}>
      <map.Icon size={18} className="mt-0.5 shrink-0" />
      <div className="min-w-0">
        {title ? <p className="font-medium">{title}</p> : null}
        {children ? <div className={cn(title && "mt-0.5", "text-[13px] leading-5 opacity-90")}>{children}</div> : null}
      </div>
    </div>
  );
}

/* ---------- Toasts ---------- */

interface Toast { id: number; tone: "success" | "danger" | "info"; message: string }
const ToastCtx = createContext<{ push: (t: Omit<Toast, "id">) => void } | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = ++counter.current;
    setToasts((all) => [...all, { ...t, id }]);
    setTimeout(() => setToasts((all) => all.filter((x) => x.id !== id)), 4000);
  }, []);
  const value = useMemo(() => ({ push }), [push]);
  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4">
        {toasts.map((t) => (
          <div key={t.id} className={cn(
            "animate-in pointer-events-auto flex items-center gap-2 rounded-md border px-3.5 py-2.5 text-sm shadow-pop",
            t.tone === "success" && "border-success/20 bg-surface text-fg",
            t.tone === "danger" && "border-danger/30 bg-surface text-fg",
            t.tone === "info" && "border-line bg-surface text-fg",
          )}>
            {t.tone === "success" ? <Icons.checkCircle size={16} className="text-success" /> : t.tone === "danger" ? <Icons.alert size={16} className="text-danger" /> : <Icons.info size={16} className="text-info" />}
            {t.message}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  return ctx ?? { push: () => {} };
}