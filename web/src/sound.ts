// The game's sounds (redesign, October 2026). Every sound is made here, from plain tones, so it is
// the game's own: no recordings are used. Sound is only for things that happen to the player:
// a trade that went through, a message, a rank case or a decision waiting, and the Closing Bell.
// News stays silent. The player turns sound off, or sets its volume, from the top bar or their menu.

export type SoundKind = "trade" | "message" | "decision" | "bell";

let enabled = true;
let volume = 30;            // 0 to 100
let context: AudioContext | null = null;

/** What the player has chosen. Called whenever the player's settings are read. */
export function setSoundSettings(on: boolean, level: number) {
  enabled = on;
  volume = Math.max(0, Math.min(100, level));
}

function audio(): AudioContext | null {
  if (typeof window === "undefined") return null;
  const Maker = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Maker) return null;
  if (!context) {
    try { context = new Maker(); } catch { return null; }
  }
  // Browsers only allow sound after the player has touched the page; until then it stays silent.
  if (context.state === "suspended") context.resume().catch(() => undefined);
  return context;
}

function tone(ctx: AudioContext, at: number, freq: number, length: number, loud: number, kind: OscillatorType = "sine") {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = kind;
  osc.frequency.setValueAtTime(freq, at);
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.0002, loud), at + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + length);
  osc.connect(gain).connect(ctx.destination);
  osc.start(at);
  osc.stop(at + length + 0.05);
}

/** Plays one of the game's sounds, if the player has sound on. Never throws. */
export function play(kind: SoundKind) {
  if (!enabled || volume === 0) return;
  const ctx = audio();
  if (!ctx || ctx.state !== "running") return;
  const loud = (volume / 100) * 0.35;
  const now = ctx.currentTime + 0.02;
  try {
    if (kind === "trade") {             // a short soft click and chime
      tone(ctx, now, 1800, 0.03, loud * 0.5, "triangle");
      tone(ctx, now + 0.04, 880, 0.35, loud);
      tone(ctx, now + 0.04, 1320, 0.30, loud * 0.4);
    } else if (kind === "message") {    // two quiet notes
      tone(ctx, now, 660, 0.16, loud * 0.8);
      tone(ctx, now + 0.14, 880, 0.22, loud * 0.8);
    } else if (kind === "decision") {   // one low bell
      tone(ctx, now, 330, 0.9, loud);
      tone(ctx, now, 660, 0.6, loud * 0.35);
      tone(ctx, now, 990, 0.35, loud * 0.15);
    } else {                            // the Closing Bell: a short exchange bell, struck twice
      for (const strike of [0, 0.45]) {
        tone(ctx, now + strike, 520, 1.3, loud);
        tone(ctx, now + strike, 1040, 0.9, loud * 0.4);
        tone(ctx, now + strike, 1560, 0.5, loud * 0.2);
      }
    }
  } catch {
    // Sound is a nicety: a device that cannot play it simply stays quiet.
  }
}

/** Wakes the sound system on the player's first touch, so later sounds are allowed to play. */
export function unlockOnFirstTouch() {
  if (typeof window === "undefined") return;
  const wake = () => { audio(); window.removeEventListener("pointerdown", wake); window.removeEventListener("keydown", wake); };
  window.addEventListener("pointerdown", wake);
  window.addEventListener("keydown", wake);
}
