"use client";

import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
import { Icons } from "@/components/ui/icons";
import type { ChatMessage } from "@/features/intake/use-intake-session";

// The assistant's own words, not the patient's - a patient typing "**test**" must stay
// literal text, so markdown is only ever parsed on the assistant side.
const MARKDOWN_COMPONENTS = {
  p: (props: React.ComponentPropsWithoutRef<"p">) => <p className="mb-2 last:mb-0" {...props} />,
  strong: (props: React.ComponentPropsWithoutRef<"strong">) => <strong className="font-semibold text-fg" {...props} />,
  em: (props: React.ComponentPropsWithoutRef<"em">) => <em className="italic" {...props} />,
  ul: (props: React.ComponentPropsWithoutRef<"ul">) => <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0" {...props} />,
  ol: (props: React.ComponentPropsWithoutRef<"ol">) => <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0" {...props} />,
  a: (props: React.ComponentPropsWithoutRef<"a">) => (
    <a className="text-brand underline underline-offset-2" target="_blank" rel="noreferrer" {...props} />
  ),
};

export function MessageList({ messages, typing }: { messages: ChatMessage[]; typing: boolean }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const count = messages.length;
  const lastLen = messages[messages.length - 1]?.content.length ?? 0;

  // Keep the newest text in view inside the conversation, without pulling the
  // whole patient portal (and its other sections) down the page.
  useEffect(() => {
    const list = scrollRef.current;
    if (list) list.scrollTo({ top: list.scrollHeight, behavior: "smooth" });
  }, [count, lastLen, typing]);

  return (
    <div ref={scrollRef} role="log" aria-live="polite" aria-relevant="additions text"
      className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
      {messages.map((m) => <Bubble key={m.id} message={m} />)}
      {typing ? (
        <div className="flex items-end gap-2.5">
          <AssistantMark />
          <div className="rounded-2xl rounded-bl-md border border-line bg-surface px-4 py-3 shadow-card">
            <span className="sr-only">Assistant is typing</span>
            <span className="flex items-center gap-1" aria-hidden="true">
              <Dot index={0} /><Dot index={1} /><Dot index={2} />
            </span>
          </div>
        </div>
      ) : null}
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
          "max-w-[85%] rounded-2xl px-4 py-2.5 text-[15px] leading-6 sm:max-w-[75%]",
          mine
            ? "whitespace-pre-wrap rounded-br-md bg-brand text-brand-fg"
            : "rounded-bl-md border border-line bg-surface text-fg shadow-card",
        )}
      >
        <span className="sr-only">{mine ? "You: " : "Assistant: "}</span>
        {mine ? message.content : <ReactMarkdown components={MARKDOWN_COMPONENTS}>{message.content}</ReactMarkdown>}
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

function Dot({ index }: { index: 0 | 1 | 2 }) {
  const delay = ["[animation-delay:0ms]", "[animation-delay:160ms]", "[animation-delay:320ms]"][index];
  return <span className={cn("h-1.5 w-1.5 animate-pulse-soft rounded-full bg-fg-subtle", delay)} />;
}
