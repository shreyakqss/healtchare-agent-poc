"use client";

import { cloneElement, forwardRef, isValidElement, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const base =
  "w-full rounded-md border border-line bg-surface px-3 text-sm text-fg placeholder:text-fg-subtle transition-colors " +
  "hover:border-line-strong focus:border-brand-ring focus:outline-none focus:ring-2 focus:ring-brand-ring/30 disabled:opacity-50";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={cn(base, "h-10", className)} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={cn(base, "min-h-24 py-2 leading-6", className)} {...rest} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, children, ...rest }, ref) {
  return (
    <select ref={ref} className={cn(base, "select-chevron h-10 appearance-none bg-no-repeat pr-9", className)} {...rest}>
      {children}
    </select>
  );
});

export function Field({ label, hint, error, required, htmlFor, children, className }: {
  label: string; hint?: ReactNode; error?: string | null; required?: boolean; htmlFor?: string; children: ReactNode; className?: string;
}) {
  const messageId = `${useId()}-message`;
  const message = error || hint;
  const control = isValidElement<{ required?: boolean; "aria-invalid"?: boolean; "aria-describedby"?: string }>(children)
    ? cloneElement(children, {
        required: required || children.props.required,
        "aria-invalid": error ? true : children.props["aria-invalid"],
        "aria-describedby": message
          ? [children.props["aria-describedby"], messageId].filter(Boolean).join(" ")
          : children.props["aria-describedby"],
      })
    : children;
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={htmlFor} className="block text-sm font-medium text-fg">
        {label}
        {required ? <span className="ml-0.5 text-danger" aria-hidden="true">*</span> : null}
      </label>
      {control}
      {error ? <p id={messageId} role="alert" className="text-xs text-danger">{error}</p> : hint ? <p id={messageId} className="text-xs text-fg-subtle">{hint}</p> : null}
    </div>
  );
}

export function Segmented<T extends string>({ value, onChange, options, label, className }: {
  value: T; onChange: (v: T) => void; options: Array<{ value: T; label: ReactNode }>; label: string; className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("inline-flex rounded-md border border-line bg-sunken p-0.5", className)}>
      {options.map((o) => (
        <button
          key={o.value} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
          className={cn(
            "h-8 rounded-sm px-3 text-sm font-medium transition-colors",
            value === o.value ? "bg-surface text-fg shadow-card" : "text-fg-muted hover:text-fg",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
