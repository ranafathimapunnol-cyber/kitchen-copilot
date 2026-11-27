"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { api } from "@/lib/api/client";
import { AGENT_ENDPOINT } from "@/lib/api/endpoints";
import { pageContext, type AgentMessage, type AgentProposal, type AgentStatus } from "@/lib/agent";
import { errorMessage } from "@/lib/payments";
import Button from "@/components/ui/Button";
import { Field, TextArea } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";

export type Conversation = { id: number; title: string; updated_at: string };
export type Thread = { id: number; title: string; messages: AgentMessage[]; proposals: AgentProposal[] };
type Reply = { conversation_id: number; title: string; question: AgentMessage; answer: AgentMessage; proposals: AgentProposal[] };

type CopilotState = {
  /** Campus users only; the API refuses everyone else. */
  available: boolean;
  status: AgentStatus | null;
  statusError: string;
  conversations: Conversation[];
  thread: Thread | null;
  sending: boolean;
  /** PENDING proposals this user may approve or reject. */
  awaiting: AgentProposal[];
  send: (text: string) => Promise<boolean>;
  newConversation: () => void;
  openConversation: (id: number) => Promise<void>;
  refreshAwaiting: () => void;
  requestDecision: (p: AgentProposal, approve: boolean) => void;
  /** Called after a decision so other views can refresh their lists. */
  onProposalChange: (listener: (p: AgentProposal) => void) => () => void;
  panelOpen: boolean;
  setPanelOpen: (open: boolean) => void;
};

const CopilotContext = createContext<CopilotState | null>(null);

export function useCopilot(): CopilotState {
  const value = useContext(CopilotContext);
  if (!value) throw new Error("useCopilot must be used inside CopilotProvider");
  return value;
}

const POLL_MS = 120_000;

/**
 * One Copilot conversation for the whole dashboard. It lives in the shell,
 * so it carries across page changes; the open conversation id is kept for
 * the browser tab (sessionStorage) so a reload reopens it. Every figure and
 * every decision goes through /api/agent, which checks the user's role,
 * permissions and campus on each call.
 */
export default function CopilotProvider({ userId, role, children }: { userId: number | string; role: string; children: ReactNode }) {
  const toast = useToast();
  const pathname = usePathname();
  const available = role !== "SUPER_ADMIN";
  const storageKey = `kc.copilot.thread.${userId}`;

  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [statusError, setStatusError] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [thread, setThread] = useState<Thread | null>(null);
  const [sending, setSending] = useState(false);
  const [awaiting, setAwaiting] = useState<AgentProposal[]>([]);
  const [panelOpen, setPanelOpen] = useState(false);
  const [decision, setDecision] = useState<{ p: AgentProposal; approve: boolean } | null>(null);
  const [note, setNote] = useState("");
  const [deciding, setDeciding] = useState(false);
  const listeners = useRef(new Set<(p: AgentProposal) => void>());
  const threadRef = useRef<Thread | null>(null);
  useEffect(() => { threadRef.current = thread; }, [thread]);

  const remember = useCallback((id: number | null) => {
    try {
      if (id) window.sessionStorage.setItem(storageKey, String(id));
      else window.sessionStorage.removeItem(storageKey);
    } catch { /* storage blocked: the conversation still lasts until reload */ }
  }, [storageKey]);

  const refreshAwaiting = useCallback(() => {
    api.get<{ items: AgentProposal[] }>(`${AGENT_ENDPOINT}/proposals?status=PENDING`)
      .then((r) => setAwaiting(r.items.filter((p) => p.can_decide)))
      .catch(() => undefined);
  }, []);

  // Status, recent conversations and the conversation open in this tab.
  useEffect(() => {
    if (!available) return;
    let active = true;
    api.get<AgentStatus>(`${AGENT_ENDPOINT}/status`)
      .then((s) => {
        if (!active) return;
        setStatus(s);
        if (!s.enabled) return;
        api.get<{ items: Conversation[] }>(`${AGENT_ENDPOINT}/conversations`)
          .then((r) => active && setConversations(r.items)).catch(() => undefined);
        let saved: string | null = null;
        try { saved = window.sessionStorage.getItem(storageKey); } catch { /* blocked */ }
        if (saved && /^\d+$/.test(saved)) {
          api.get<Thread>(`${AGENT_ENDPOINT}/conversations/${saved}`)
            .then((t) => active && setThread(t))
            .catch(() => remember(null));
        }
      })
      .catch((err: unknown) => active && setStatusError(errorMessage(err, "Unable to reach Kitchen Copilot.")));
    return () => { active = false; };
  }, [available, storageKey, remember]);

  // Approvals waiting for this user: on start, every two minutes while the
  // tab is visible, and when the tab becomes visible again.
  useEffect(() => {
    if (!status?.enabled) return;
    refreshAwaiting();
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") refreshAwaiting(); }, POLL_MS);
    const onVisible = () => { if (document.visibilityState === "visible") refreshAwaiting(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", onVisible); };
  }, [status?.enabled, refreshAwaiting]);

  const send = useCallback(async (message: string): Promise<boolean> => {
    const body = message.trim();
    if (body.length < 2 || sending) return false;
    setSending(true);
    const current = threadRef.current;
    const pending: AgentMessage = { id: -1, role: "user", content: body, payload: {}, created_at: new Date().toISOString() };
    setThread((t) => t ? { ...t, messages: [...t.messages, pending] } : { id: 0, title: body, messages: [pending], proposals: [] });
    try {
      const r = await api.post<Reply>(`${AGENT_ENDPOINT}/messages`,
        { text: body, conversation_id: current?.id || null, page: pageContext(pathname) });
      setThread((t) => ({
        id: r.conversation_id, title: r.title,
        messages: [...(t?.messages ?? []).filter((m) => m.id !== -1), r.question, r.answer],
        proposals: [...(t?.proposals ?? []), ...r.proposals],
      }));
      remember(r.conversation_id);
      setConversations((list) => [{ id: r.conversation_id, title: r.title, updated_at: r.answer.created_at },
        ...list.filter((c) => c.id !== r.conversation_id)]);
      if (r.proposals.length) refreshAwaiting();
      return true;
    } catch (err) {
      setThread((t) => {
        if (!t) return null;
        const messages = t.messages.filter((m) => m.id !== -1);
        return t.id || messages.length ? { ...t, messages } : null;
      });
      toast.error(errorMessage(err, "Kitchen Copilot could not answer."));
      return false;
    } finally {
      setSending(false);
    }
  }, [sending, pathname, remember, refreshAwaiting, toast]);

  const newConversation = useCallback(() => { setThread(null); remember(null); }, [remember]);

  const openConversation = useCallback(async (id: number) => {
    try {
      setThread(await api.get<Thread>(`${AGENT_ENDPOINT}/conversations/${id}`));
      remember(id);
    } catch (err) {
      toast.error(errorMessage(err, "Unable to open the conversation."));
    }
  }, [remember, toast]);

  const requestDecision = useCallback((p: AgentProposal, approve: boolean) => { setNote(""); setDecision({ p, approve }); }, []);

  const onProposalChange = useCallback((listener: (p: AgentProposal) => void) => {
    listeners.current.add(listener);
    return () => { listeners.current.delete(listener); };
  }, []);

  async function decide() {
    if (!decision) return;
    setDeciding(true);
    try {
      const updated = await api.post<AgentProposal>(
        `${AGENT_ENDPOINT}/proposals/${decision.p.id}/${decision.approve ? "approve" : "reject"}`,
        decision.approve ? { note: note.trim() || null } : { reason: note.trim() });
      setThread((t) => t ? { ...t, proposals: t.proposals.map((x) => x.id === updated.id ? updated : x) } : t);
      setAwaiting((list) => list.filter((x) => x.id !== updated.id));
      listeners.current.forEach((fn) => fn(updated));
      if (updated.status === "EXECUTED") toast.success(`Created ${updated.result.number ?? ""}. It stays a draft until you finish it on its screen.`);
      else if (updated.status === "FAILED") toast.error(`Not created: ${updated.error}`);
      else toast.success("Proposal rejected.");
      setDecision(null);
    } catch (err) {
      toast.error(errorMessage(err, "The decision could not be saved."));
      refreshAwaiting();
    } finally {
      setDeciding(false);
    }
  }

  const value = useMemo<CopilotState>(() => ({
    available, status, statusError, conversations, thread, sending, awaiting,
    send, newConversation, openConversation, refreshAwaiting, requestDecision, onProposalChange,
    panelOpen, setPanelOpen,
  }), [available, status, statusError, conversations, thread, sending, awaiting, send, newConversation,
    openConversation, refreshAwaiting, requestDecision, onProposalChange, panelOpen]);

  return (
    <CopilotContext.Provider value={value}>
      {children}
      <Modal open={decision !== null} onClose={() => !deciding && setDecision(null)} size="sm" dismissible={!deciding}
        title={decision?.approve ? "Approve this action?" : "Reject this proposal?"}
        description={decision?.p.title}
        footer={<>
          <Button variant="secondary" onClick={() => setDecision(null)} disabled={deciding}>Cancel</Button>
          <Button variant={decision?.approve ? "primary" : "danger"} loading={deciding}
            disabled={!decision?.approve && note.trim().length < 3} onClick={decide}>
            {decision?.approve ? "Approve and create" : "Reject"}
          </Button>
        </>}>
        <div className="space-y-3 text-sm">
          {decision?.approve && (
            <p className="text-slate-600">Your permission is checked again now. The record is created through the normal application rules and recorded in the audit log under your name. It is saved as a draft or request; nothing is posted to stock or sent to a supplier.</p>
          )}
          <Field label={decision?.approve ? "Note (optional)" : "Reason"} required={!decision?.approve}>
            {({ id }) => <TextArea id={id} rows={3} value={note} onChange={(e) => setNote(e.target.value)} data-autofocus />}
          </Field>
        </div>
      </Modal>
    </CopilotContext.Provider>
  );
}
