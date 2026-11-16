"use client";

import type { Message } from "@/hooks/useConversation";
import type { Dictionary } from "@/lib/i18n/config";

type Props = {
  t: Dictionary;
  messages: Message[];
  lastUser: Message | undefined;
  assistantText: (message: Extract<Message, { role: "assistant" }>) => string;
  open: boolean;
  onToggle: () => void;
};

/** The visitor's last message plus a History toggle that reveals the whole conversation. */
export function Transcript({ t, messages, lastUser, assistantText, open, onToggle }: Props) {
  if (!lastUser || lastUser.role !== "user") return null;

  return (
    <div className="relative">
      <div className="flex items-center gap-3 text-sm">
        <p className="min-w-0 flex-1 truncate text-mist-400">
          <span className="text-mist-200">{t.conversation.you}:</span> {lastUser.text}
        </p>
        <button
          type="button"
          aria-expanded={open}
          aria-controls="conversation-history"
          onClick={onToggle}
          className="shrink-0 rounded-full border border-ink-700 px-3 py-1 text-xs text-mist-200 transition-colors hover:border-accent/60 hover:text-mist-50"
        >
          {t.conversation.history}
        </button>
      </div>

      {open && (
        <section
          id="conversation-history"
          aria-label={t.conversation.historyTitle}
          className="absolute inset-x-0 bottom-full z-20 mb-3 max-h-[45dvh] overflow-y-auto rounded-2xl border border-ink-700 bg-ink-900 p-4 shadow-2xl"
        >
          <h2 className="mb-3 font-mono text-xs uppercase tracking-[0.18em] text-mist-400">
            {t.conversation.historyTitle}
          </h2>
          <ol className="space-y-3 text-sm">
            {messages.map((message) => (
              <li key={message.id}>
                <span className={`block text-xs ${message.role === "user" ? "text-mist-400" : "text-accent"}`}>
                  {message.role === "user" ? t.conversation.you : t.conversation.assistant}
                </span>
                <span className="text-mist-200">
                  {message.role === "user" ? message.text : assistantText(message)}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
