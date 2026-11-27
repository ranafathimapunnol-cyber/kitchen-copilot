"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowUp, ClipboardSignature, Maximize2, MessageSquarePlus, Minus, ShieldAlert, X } from "lucide-react";

import { pageTopic, suggestionsFor } from "@/lib/agent";
import { findNavEntry } from "@/lib/navigation";
import { cn } from "@/components/ui/cn";
import { Answer, CopilotMark, ProposalCard, Thinking } from "./CopilotParts";
import { useCopilot } from "./CopilotProvider";

const DOCK_OFFSET = "4.75rem"; // launcher height + gap; toasts sit above it

function HeaderButton({ label, onClick, children, href }: { label: string; onClick?: () => void; children: React.ReactNode; href?: string }) {
  const cls = "flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900";
  return href ? (
    <Link href={href} aria-label={label} title={label} className={cls} onClick={onClick}>{children}</Link>
  ) : (
    <button type="button" aria-label={label} title={label} className={cls} onClick={onClick}>{children}</button>
  );
}

/**
 * The floating Kitchen Copilot: a launcher at the bottom right of every
 * dashboard screen and a chat panel that keeps one conversation across
 * screens. It sends the screen being viewed with each question (which only
 * focuses the answer) and shows proposals waiting for this user's decision.
 */
export default function CopilotDock({ hidden = false }: { hidden?: boolean }) {
  const pathname = usePathname();
  const c = useCopilot();
  const [text, setText] = useState("");
  const [tab, setTab] = useState<"chat" | "approvals">("chat");
  const input = useRef<HTMLTextAreaElement>(null);
  const launcher = useRef<HTMLButtonElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const onFullPage = pathname === "/dashboard/copilot" || pathname.startsWith("/dashboard/copilot/");
  const shown = c.available && !hidden && !onFullPage;
  const open = shown && c.panelOpen;
  const enabled = Boolean(c.status?.enabled);
  const waiting = enabled ? c.awaiting.length : 0;

  // Toasts move up so they never sit on the launcher.
  useEffect(() => {
    if (!shown) return;
    const root = document.documentElement;
    root.style.setProperty("--kc-dock-offset", DOCK_OFFSET);
    return () => { root.style.removeProperty("--kc-dock-offset"); };
  }, [shown]);

  // Focus the message box once the panel has become visible (it is
  // visibility:hidden, so not focusable, until the opening frame).
  useEffect(() => {
    if (!open || tab !== "chat") return;
    const timer = window.setTimeout(() => input.current?.focus({ preventScroll: true }), 60);
    return () => window.clearTimeout(timer);
  }, [open, tab, enabled]);

  useEffect(() => {
    if (open) end.current?.scrollIntoView({ block: "end" });
  }, [open, c.thread?.messages.length, c.sending]);

  if (!shown) return null;

  const minimise = () => { c.setPanelOpen(false); launcher.current?.focus(); };
  const submit = async (message: string) => {
    if (message.trim().length < 2) return;
    setTab("chat");
    setText("");
    if (!(await c.send(message))) setText(message);
  };

  const where = findNavEntry(pathname)?.item.label ?? (pathname === "/dashboard" ? "Dashboard" : null);
  const suggestions = c.status ? suggestionsFor(pageTopic(pathname) ? pathname : "/dashboard", c.status.workflows) : [];
  const messages = c.thread?.messages ?? [];

  return (
    <div
      className="fixed z-[35] print:hidden"
      style={{ right: "max(1rem, env(safe-area-inset-right, 0px))", bottom: "max(1rem, env(safe-area-inset-bottom, 0px))" }}
      onKeyDown={(e) => { if (e.key === "Escape" && open && !e.defaultPrevented) { e.stopPropagation(); minimise(); } }}
    >
      <section
        id="copilot-panel"
        role="dialog"
        aria-modal="false"
        aria-label="Kitchen Copilot"
        aria-hidden={!open}
        inert={!open}
        data-copilot-panel={open ? "open" : "closed"}
        className={cn(
          "fixed inset-0 flex flex-col overflow-hidden bg-slate-50 transition-[opacity,transform,visibility] duration-200 ease-out",
          "sm:absolute sm:inset-auto sm:right-0 sm:bottom-[calc(100%+0.75rem)] sm:h-[min(42rem,calc(100dvh-8.5rem))] sm:w-[25rem] sm:origin-bottom-right sm:rounded-2xl sm:border sm:border-slate-200 sm:shadow-overlay",
          open ? "visible translate-y-0 scale-100 opacity-100" : "pointer-events-none invisible translate-y-3 scale-[0.97] opacity-0",
        )}
        style={{ paddingTop: "env(safe-area-inset-top, 0px)" }}
      >
        <header className="flex shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-4 py-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white"><CopilotMark size={19} /></span>
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-[15px] font-semibold tracking-tight text-slate-900">Kitchen Copilot</p>
            <p className="mt-0.5 flex items-center gap-1.5 truncate text-[11.5px] text-slate-500">
              <span aria-hidden className={cn("h-1.5 w-1.5 shrink-0 rounded-full", enabled ? "bg-emerald-500" : "bg-slate-400")} />
              {!c.status ? (c.statusError ? "Unavailable" : "Connecting…")
                : !enabled ? "Turned off"
                  : c.status.reader === "gemini" ? `Language model: ${c.status.external_model}` : "Built-in reader · no external AI"}
            </p>
          </div>
          {enabled && <HeaderButton label="New conversation" onClick={() => { c.newConversation(); setTab("chat"); }}><MessageSquarePlus size={17} /></HeaderButton>}
          <HeaderButton label="Open full screen" href="/dashboard/copilot" onClick={() => c.setPanelOpen(false)}><Maximize2 size={16} /></HeaderButton>
          <HeaderButton label="Minimise" onClick={minimise}><Minus size={18} /></HeaderButton>
        </header>

        {enabled && (
          <div className="flex shrink-0 items-center gap-1 border-b border-slate-200 bg-white px-3 py-2" role="tablist" aria-label="Copilot views">
            {(["chat", "approvals"] as const).map((t) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                className={cn("flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium transition-colors",
                  tab === t ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100")}>
                {t === "chat" ? "Chat" : "Approvals"}
                {t === "approvals" && waiting > 0 && (
                  <span className="rounded-full bg-[#d9f18d] px-1.5 text-[11px] leading-4 font-semibold text-[#202522]">{waiting}</span>
                )}
              </button>
            ))}
            {where && tab === "chat" && (
              <span className="ml-auto truncate rounded-full border border-slate-200 px-2.5 py-1 text-[11px] text-slate-500" title="Copilot focuses on the screen you are viewing">
                Viewing: <span className="font-medium text-slate-700">{where}</span>
              </span>
            )}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4" data-copilot-body>
          {c.statusError ? (
            <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{c.statusError}</p>
          ) : !c.status ? (
            <Thinking label="Connecting…" />
          ) : !enabled ? (
            <div className="space-y-3 py-6 text-center">
              <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-500"><ShieldAlert size={22} aria-hidden /></span>
              <p className="font-semibold text-slate-900">Kitchen Copilot is turned off</p>
              <p className="text-sm text-slate-600">An administrator can turn it on with the AGENT_ENABLED setting. Every other screen works normally while it is off.</p>
            </div>
          ) : tab === "approvals" ? (
            c.awaiting.length === 0 ? (
              <div className="space-y-2 py-8 text-center">
                <ClipboardSignature size={22} aria-hidden className="mx-auto text-slate-400" />
                <p className="font-semibold text-slate-900">Nothing waiting for you</p>
                <p className="text-sm text-slate-600">Proposals you are allowed to approve appear here. Copilot never approves its own.</p>
              </div>
            ) : (
              <div className="space-y-3" data-copilot-approvals>
                {c.awaiting.map((p) => (
                  <div key={p.id} className="space-y-1">
                    <p className="text-xs text-slate-500">Asked by {p.created_by_name}</p>
                    <ProposalCard p={p} onDecide={c.requestDecision} compact />
                  </div>
                ))}
              </div>
            )
          ) : messages.length === 0 ? (
            <div className="space-y-4 pt-2">
              <div>
                <p className="text-xl font-semibold tracking-tight text-slate-900">How can I help?</p>
                <p className="mt-1 text-sm leading-relaxed text-slate-600">
                  I read your campus records through the same permission checks as the screens, show what I checked, and prepare actions that only happen when a person approves them.
                </p>
              </div>
              {suggestions.length > 0 ? (
                <ul className="space-y-2" aria-label="Suggested questions">
                  {suggestions.map((s) => (
                    <li key={s.text}>
                      <button type="button" disabled={c.sending} onClick={() => void submit(s.text)}
                        className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-left text-sm text-slate-800 transition-colors hover:border-slate-900 disabled:opacity-50">
                        {s.text}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-slate-500">Your account has none of the permissions Copilot&rsquo;s jobs need. Ask your Admin if you need them.</p>
              )}
            </div>
          ) : (
            <div className="space-y-5" data-copilot-thread>
              {messages.map((m) => m.role === "user" ? (
                <div key={m.id} className="flex justify-end">
                  <p className="max-w-[85%] rounded-2xl rounded-br-md bg-slate-900 px-3.5 py-2 text-sm leading-relaxed text-white">{m.content}</p>
                </div>
              ) : (
                <Answer key={m.id} m={m} proposals={c.thread?.proposals ?? []} onChoice={(t) => void submit(t)}
                  onDecide={c.requestDecision} busy={c.sending} compact />
              ))}
              {c.sending && <Thinking />}
              <div ref={end} />
            </div>
          )}
        </div>

        {enabled && tab === "chat" && (
          <form className="shrink-0 border-t border-slate-200 bg-white p-3" style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom, 0px))" }}
            onSubmit={(e) => { e.preventDefault(); void submit(text); }}>
            <div className="flex items-end gap-2 rounded-xl border border-slate-300 bg-white p-1.5 pl-3 transition-[border-color,box-shadow] focus-within:border-slate-900 focus-within:ring-4 focus-within:ring-[#d9f18d]/40">
              <label htmlFor="copilot-dock-input" className="sr-only">Message Kitchen Copilot</label>
              <textarea id="copilot-dock-input" ref={input} rows={1} value={text} maxLength={1000}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void submit(text); } }}
                placeholder="Ask about this screen…"
                className="max-h-32 min-h-9 min-w-0 flex-1 resize-none border-0 bg-transparent py-1.5 text-sm text-slate-900 [field-sizing:content] placeholder:text-slate-400 focus:outline-none" />
              <button type="submit" aria-label="Send" disabled={c.sending || text.trim().length < 2}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white transition-opacity disabled:opacity-35">
                <ArrowUp size={17} aria-hidden />
              </button>
            </div>
            <p className="mt-1.5 px-1 text-[11px] text-slate-500">Enter to send · Nothing changes until a person approves it.</p>
          </form>
        )}
      </section>

      <button
        ref={launcher}
        type="button"
        onClick={() => c.setPanelOpen(!open)}
        aria-expanded={open}
        aria-controls="copilot-panel"
        aria-label={open ? "Minimise Kitchen Copilot" : `Open Kitchen Copilot${waiting ? `, ${waiting} waiting for your approval` : ""}`}
        data-copilot-launcher
        className={cn(
          "relative flex h-14 w-14 items-center justify-center rounded-full bg-slate-900 text-white shadow-raised ring-4 ring-[#d9f18d]/45 transition-[transform,box-shadow] duration-200 hover:scale-105 hover:ring-[#d9f18d]/70 active:scale-95",
          open && "max-sm:hidden",
        )}
      >
        <span className={cn("transition-transform duration-200", open && "rotate-90")}>
          {open ? <X size={22} aria-hidden /> : <CopilotMark size={27} />}
        </span>
        {waiting > 0 && !open && (
          <span className="absolute -top-0.5 -right-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-[#d9f18d] px-1 text-[11px] font-bold text-[#202522] ring-2 ring-slate-50" data-copilot-badge>
            {waiting > 9 ? "9+" : waiting}
          </span>
        )}
      </button>
    </div>
  );
}
