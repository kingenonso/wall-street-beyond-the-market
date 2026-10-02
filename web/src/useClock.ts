import { useEffect, useRef, useState } from "react";
import { api, type Clock } from "./api";

export type LiveClock = { clock: Clock; now: Date; msToNextChange: number };

/**
 * Keeps the Lagos clock ticking on screen.
 *
 * The time shown always comes from the server, never from the player's own
 * device, whose clock may be wrong. We ask the server once a minute, note how
 * far the device's clock is from the server's, and tick every second between.
 */
export function useClock(): LiveClock | null {
  const [clock, setClock] = useState<Clock | null>(null);
  const [tick, setTick] = useState(() => Date.now());
  const offset = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const fresh = await api.clock();
        if (cancelled) return;
        offset.current = new Date(fresh.lagos_time).getTime() - Date.now();
        setClock(fresh);
      } catch {
        // Keep showing the last known clock; the next refresh will try again.
      }
    };
    refresh();
    const everyMinute = setInterval(refresh, 60_000);
    const everySecond = setInterval(() => setTick(Date.now()), 1000);
    return () => {
      cancelled = true;
      clearInterval(everyMinute);
      clearInterval(everySecond);
    };
  }, []);

  // When the market is due to change state, ask the server straight away.
  const nextChange = clock ? new Date(clock.next_change_at).getTime() : null;
  const serverNow = tick + offset.current;
  useEffect(() => {
    if (nextChange !== null && serverNow >= nextChange) {
      api.clock().then(setClock).catch(() => undefined);
    }
  }, [nextChange, serverNow >= (nextChange ?? Infinity)]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!clock) return null;
  return { clock, now: new Date(serverNow), msToNextChange: (nextChange ?? serverNow) - serverNow };
}
