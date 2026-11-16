// Live events, part 2 (owner, 16 November 2026): updates that appear the moment something changes.
//
// The page keeps one quiet line open to the server (/api/live/stream). The server says only what kind of thing changed (a
// bell, a prediction, a chat message, the standing plan); the page then loads itself again, so everything shown still
// comes from the page the server sends, with only what this player may see. If the line drops, the browser opens it
// again by itself, and the page looks again in case it missed something meanwhile.

import { useEffect, useRef, useState } from "react";

export type PushKind = "event" | "prediction" | "chat" | "plan";

/** Pings arriving close together (many members sealing at once) become one reload. */
export const GATHER_MS = 250;

/** Of the kinds in a "changed" message, those this screen cares about. */
export function wanted(data: string, only?: readonly PushKind[]): PushKind[] {
  let kinds: unknown;
  try {
    kinds = (JSON.parse(data) as { what?: unknown }).what;
  } catch {
    return [];
  }
  if (!Array.isArray(kinds)) return [];
  const known: PushKind[] = ["event", "prediction", "chat", "plan"];
  return kinds.filter((k): k is PushKind => known.includes(k as PushKind) && (!only || only.includes(k as PushKind)));
}

type Listener = { kinds?: readonly PushKind[]; call: (what: PushKind[]) => void; setOpen: (open: boolean) => void };

/** One line per browser tab, shared by every part of the page that listens; closed when the last one stops. */
const listeners = new Set<Listener>();
let source: EventSource | null = null;
let isOpen = false;
let before = false;
let timer: number | undefined;
const pending = new Set<PushKind>();

function tell(what: PushKind[]) {
  for (const l of listeners) {
    const mine = l.kinds ? what.filter((k) => l.kinds!.includes(k)) : what;
    if (mine.length) l.call(mine);
  }
}

function setAll(open: boolean) {
  isOpen = open;
  for (const l of listeners) l.setOpen(open);
}

function connect() {
  if (source || typeof EventSource === "undefined") return;
  before = false;
  const line = new EventSource("/api/live/stream");
  source = line;
  line.addEventListener("hello", () => {
    setAll(true);
    // Back after a dropped line: something may have happened meanwhile.
    if (before) tell(["event", "prediction", "chat", "plan"]);
    before = true;
  });
  line.addEventListener("changed", (message) => {
    const what = wanted((message as MessageEvent<string>).data);
    if (!what.length) return;
    what.forEach((k) => pending.add(k));
    if (timer === undefined) {
      timer = window.setTimeout(() => {
        timer = undefined;
        const all = [...pending];
        pending.clear();
        tell(all);
      }, GATHER_MS);
    }
  });
  line.addEventListener("bye", () => disconnect());
  line.onerror = () => setAll(false);
}

function disconnect() {
  source?.close();
  source = null;
  if (timer !== undefined) window.clearTimeout(timer);
  timer = undefined;
  pending.clear();
  setAll(false);
}

/** Calls `onChange` the moment the server says something changed. True while the line is open. */
export function useLivePushes(onChange: (what: PushKind[]) => void, only?: readonly PushKind[]): boolean {
  const [open, setOpen] = useState(isOpen);
  const latest = useRef(onChange);
  latest.current = onChange;
  const onlyKey = only ? only.join(",") : "";
  useEffect(() => {
    const me: Listener = {
      kinds: onlyKey ? (onlyKey.split(",") as PushKind[]) : undefined,
      call: (what) => latest.current(what),
      setOpen,
    };
    listeners.add(me);
    setOpen(isOpen);
    connect();
    return () => {
      listeners.delete(me);
      if (listeners.size === 0) disconnect();
    };
  }, [onlyKey]);
  return open;
}
