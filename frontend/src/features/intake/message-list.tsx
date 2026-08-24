"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { Icons } from "@/components/ui/icons";
import type { ChatMessage } from "@/features/intake/use-intake-session";

export function MessageList({ messages, typing }: { messages: ChatMessage[]; typing: boolean }) {
  const endRef = useRef<HTMLDivElement>(null);
  const count = messages.length;
  const lastLen = messages[messages.length - 1]?.content.length ?? 0;

  // Keep the newest text in view as it arrives (DOM side effect, no state).
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [count, lastLen, typing]);

  return (
    <div role="log" aria-live="polite" aria-relevant="additions text" className="space-y-4">
      {messages.map((m) => <Bubble key={m.id} message={m} />)}
      {typing ? (
        <div className="flex items-end gap-2.5">
          <AssistantMark />
          <div className="rounded-2xl rounded-bl-md border border-line bg-surface px-4 py-3 shadow-card">
            <span className="sr-only">Assistant is typing</span>
            <span className="flex items-center gap-1" aria-hidden="true">
              <Dot delay="0ms" /><Dot delay="160ms" /><Dot delay="320ms" />
            </span>
          </div>
        </div>
      ) : null}
      <div ref={endRef} />
    </div>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  const mine = message.role === "patient";
  if (!mine && message.content === "") return null;
  return (
    <div className={cn("flex items-end gap-2.5", mine && "flex-row-reverse")}>
      {mine ? null : <AssistantMark />}
      <div
        className={cn(
          "max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-[15px] leading-6 sm:max-w-[75%]",
          mine ? "rounded-br-md bg-brand text-brand-fg" : "rounded-bl-md border border-line bg-surface text-fg shadow-card",
        )}
      >
        <span className="sr-only">{mine ? "You: " : "Assistant: "}</span>
        {message.content}
        {message.streaming && message.content ? (
          <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-pulse-soft bg-current align-middle" aria-hidden="true" />
        ) : null}
      </div>
    </div>
  );
}

function AssistantMark() {
  return (
    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand" aria-hidden="true">
      <Icons.bot size={15} />
    </span>
  );
}

function Dot({ delay }: { delay: string }) {
  return <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-fg-subtle" style={{ animationDelay: delay }} />;
}