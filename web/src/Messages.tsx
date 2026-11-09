// Messages between players (quick fixes, October 2026). Reached from the menu under the profile picture.
// A player writes to another by their display name. Either may block the other; a message can be
// reported, and the sender is never told who reported or blocked them.

import { useEffect, useRef, useState } from "react";
import { api, ApiError, type ChatMessage, type Conversations, type Thread } from "./api";
import { useLoad } from "./hooks";
import { Failed, Loading, Panel } from "./Shell";

/** The player named in an address such as #/messages/Ada%20Obi. A broken address names nobody. */
export function partnerFrom(item: string | undefined): string | undefined {
  if (!item) return undefined;
  try {
    const name = decodeURIComponent(item).trim();
    return name && name.length <= 40 ? name : undefined;
  } catch {
    return undefined;
  }
}

const when = (iso: string) => new Date(iso).toLocaleString("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const go = (name?: string) => { window.location.hash = name ? `#/messages/${encodeURIComponent(name)}` : "#/messages"; };
const problem = (error: unknown) => (error instanceof ApiError ? error.message : "Could not reach the server.");

function ConversationList({ data, current }: { data: Conversations; current?: string }) {
  if (data.conversations.length === 0) return <p className="muted small">No messages yet. Write to a player by their display name.</p>;
  return (
    <ul className="conversation-list">
      {data.conversations.map((c) => (
        <li key={c.name} className={c.name === current ? "current" : undefined}>
          <a href={`#/messages/${encodeURIComponent(c.name)}`} className="plain-link">
            <span className="row">
              <span className="strong">{c.name}{c.blocked && <span className="muted small"> · ⊘ blocked</span>}</span>
              <span className="muted small">{when(c.sent_at)}</span>
            </span>
            <span className="row">
              <span className="muted small conversation-preview">{c.mine ? "You: " : ""}{c.preview}</span>
              {c.unread > 0 && <span className="count" aria-label={`${c.unread} unread`}>{c.unread}</span>}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

function ReportBox({ message, onDone, onCancel }: { message: ChatMessage; onDone: (block: boolean, reason: string) => Promise<void>; onCancel: () => void }) {
  const [reason, setReason] = useState("");
  const [block, setBlock] = useState(true);
  const [busy, setBusy] = useState(false);
  return (
    <div className="report-box">
      <label className="field-label" htmlFor={`reason-${message.id}`}>What is wrong with this message? (optional)</label>
      <input id={`reason-${message.id}`} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
      <label className="small check-line"><input type="checkbox" checked={block} onChange={(e) => setBlock(e.target.checked)} /> Also block this player</label>
      <div className="step-actions">
        <button className="button-primary" disabled={busy} onClick={() => { setBusy(true); onDone(block, reason).finally(() => setBusy(false)); }}>Send the report</button>
        <button className="button-quiet" onClick={onCancel}>Cancel</button>
      </div>
      <p className="muted small">The player is not told who reported them.</p>
    </div>
  );
}

function ThreadView({ name, limits, onChanged, onLoggedOut }: {
  name: string; limits: Conversations["limits"]; onChanged: () => void; onLoggedOut: () => void;
}) {
  const thread = useLoad<Thread>(() => api.thread(name), `thread:${name}`, onLoggedOut);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reporting, setReporting] = useState<number | null>(null);
  const [sureClear, setSureClear] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  // Opening a conversation marks it read: the list and the dot under the picture are read again.
  useEffect(() => { if (thread.data) onChanged(); }, [thread.data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { end.current?.scrollIntoView?.({ block: "nearest" }); }, [thread.data]);

  /** Runs one request. True when it worked: only then is the box emptied or the page left. */
  async function act(action: () => Promise<unknown>): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      await action();
      thread.reload();
      onChanged();
      return true;
    } catch (e) {
      setError(problem(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  if (thread.loading && !thread.data) return <Loading what="the conversation" />;
  if (thread.error) return <Failed message={thread.error} onRetry={thread.reload} />;
  const t = thread.data!;
  return (
    <Panel title={`With ${t.name}`} aside={t.blocked ? "⊘ You have blocked this player" : undefined}>
      <div className="thread" aria-live="polite">
        {t.messages.length === 0 && <p className="muted small">Nothing yet. Say hello.</p>}
        {t.messages.map((m) => (
          <div key={m.id} className={m.mine ? "bubble mine" : "bubble theirs"}>
            <div className="bubble-body">{m.body}</div>
            <div className="bubble-meta muted small">
              {m.mine ? "→ You" : `← ${t.name}`} · {when(m.sent_at)}{m.mine && m.read ? " · read" : ""}
              {!m.mine && (m.reported
                ? <span> · reported</span>
                : <> · <button className="link-button" onClick={() => setReporting(m.id)}>Report</button></>)}
            </div>
            {reporting === m.id && (
              <ReportBox message={m} onCancel={() => setReporting(null)}
                onDone={(block, reason) => act(() => api.reportMessage(m.id, reason, block)).then((ok) => { if (ok) setReporting(null); })} />
            )}
          </div>
        ))}
        <div ref={end} />
      </div>
      {t.can_write ? (
        <form className="compose" onSubmit={(e) => { e.preventDefault(); if (text.trim()) act(() => api.sendMessage(t.name, text)).then((ok) => { if (ok) setText(""); }); }}>
          <label className="field-label" htmlFor="message-text">Your message</label>
          <textarea id="message-text" rows={3} maxLength={limits.max_chars} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="row">
            <span className="muted small">{text.length} / {limits.max_chars}</span>
            <button className="button-primary" disabled={busy || !text.trim()}>Send</button>
          </div>
        </form>
      ) : <p className="muted small">⊘ You have blocked {t.name}. Unblock them to write.</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="step-actions">
        {t.blocked
          ? <button className="button-quiet" disabled={busy} onClick={() => act(() => api.unblockPlayer(t.name))}>Unblock {t.name}</button>
          : <button className="button-quiet" disabled={busy} onClick={() => act(() => api.blockPlayer(t.name))}>⊘ Block {t.name}</button>}
        {sureClear
          ? <span className="small">Clear this conversation from your list? {t.name} keeps their copy.{" "}
              <button className="button-quiet" disabled={busy} onClick={() => act(() => api.clearConversation(t.name)).then((ok) => { if (ok) go(); })}>Yes, clear it</button>{" "}
              <button className="button-quiet" onClick={() => setSureClear(false)}>No</button></span>
          : <button className="button-quiet" onClick={() => setSureClear(true)}>Clear conversation</button>}
      </div>
    </Panel>
  );
}

function NewMessage({ limits, onSent }: { limits: Conversations["limits"]; onSent: (to: string) => void }) {
  const [to, setTo] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function send() {
    setBusy(true);
    setError(null);
    try {
      await api.sendMessage(to.trim(), text);
      setText("");
      onSent(to.trim());
    } catch (e) {
      setError(problem(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="Write to a player">
      <form className="compose" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <label className="field-label" htmlFor="message-to">To (their display name)</label>
        <input id="message-to" maxLength={40} value={to} onChange={(e) => setTo(e.target.value)} />
        <label className="field-label" htmlFor="message-new">Message</label>
        <textarea id="message-new" rows={3} maxLength={limits.max_chars} value={text} onChange={(e) => setText(e.target.value)} />
        <div className="row">
          <span className="muted small">{text.length} / {limits.max_chars}</span>
          <button className="button-primary" disabled={busy || !to.trim() || !text.trim()}>Send</button>
        </div>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
    </Panel>
  );
}

export function MessagesWork({ with: other, onLoggedOut, onChanged }: { with?: string; onLoggedOut: () => void; onChanged: () => void }) {
  const list = useLoad<Conversations>(() => api.conversations(), "conversations", onLoggedOut);
  function changed() {
    list.reload();
    onChanged();
  }
  if (list.loading && !list.data) return <Loading what="your messages" />;
  if (list.error) return <Failed message={list.error} onRetry={list.reload} />;
  const data = list.data!;
  return (
    <>
      <h1>Messages</h1>
      <div className="messages-layout">
        <Panel title="Conversations" aside={data.unread > 0 ? `${data.unread} unread` : undefined}>
          <ConversationList data={data} current={other} />
          {other && <p className="small"><a href="#/messages">+ Write to someone new</a></p>}
          {data.blocked.length > 0 && (
            <>
              <div className="why-title">Blocked</div>
              <ul className="plain-list small">
                {data.blocked.map((name) => (
                  <li key={name} className="row">
                    <span>⊘ {name}</span>
                    <button className="link-button" onClick={() => api.unblockPlayer(name).then(changed).catch(() => undefined)}>Unblock</button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Panel>
        {other
          ? <ThreadView key={other} name={other} limits={data.limits} onChanged={changed} onLoggedOut={onLoggedOut} />
          : <NewMessage limits={data.limits} onSent={(to) => { changed(); go(to); }} />}
      </div>
    </>
  );
}

export function MessagesRail() {
  return (
    <Panel title="How messages work">
      <ul className="plain-list small">
        <li>▸ Write to any player by their display name.</li>
        <li>▸ Blocking means you no longer receive anything from that player. They are not told.</li>
        <li>▸ Report a message that is abusive. Three different players reporting someone in a week leaves them able only to answer people who wrote first, for that week.</li>
        <li>▸ To keep things calm: at most 30 messages an hour, 10 new people a day, and 3 messages in a row to someone who has not answered.</li>
        <li>▸ Never share passwords or real-world payment details. There is no real money in this game.</li>
      </ul>
    </Panel>
  );
}
