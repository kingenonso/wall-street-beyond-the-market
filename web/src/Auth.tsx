import { useState, type FormEvent } from "react";
import { api, ApiError, type Player, type ProfileIcon, type SignUpPending } from "./api";
import { formatLagosTime } from "./format";
import { ProfilePicture } from "./icons";
import { Wordmark } from "./Shell";
import { MarketPill } from "./Ticker";
import type { LiveClock } from "./useClock";

type Mode = "login" | "signup";

export function IconChoice({ value, onChange }: { value: ProfileIcon | null; onChange: (icon: ProfileIcon) => void }) {
  return (
    <div className="icon-choice" role="group" aria-label="Profile picture">
      {(["male", "female"] as const).map((icon) => (
        <button
          key={icon}
          type="button"
          className={value === icon ? "icon-option chosen" : "icon-option"}
          aria-pressed={value === icon}
          onClick={() => onChange(icon)}
        >
          <ProfilePicture icon={icon} name="" size={56} />
          <span>{icon === "male" ? "Male icon" : "Female icon"}</span>
        </button>
      ))}
    </div>
  );
}

export function Auth({ live, onSignedIn }: { live: LiveClock | null; onSignedIn: (player: Player) => void }) {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [icon, setIcon] = useState<ProfileIcon | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Set once sign-up details are accepted and a code has been sent to the email address.
  const [pending, setPending] = useState<SignUpPending | null>(null);
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    if (mode === "signup" && icon === null) {
      setError("Choose a profile picture: the male icon or the female icon.");
      return;
    }
    setBusy(true);
    try {
      if (mode === "login") {
        onSignedIn(await api.login(email, password));
      } else {
        const wasWaiting = pending !== null;
        setPending(await api.signup({ email, display_name: displayName, password, date_of_birth: dateOfBirth, profile_icon: icon! }));
        setCode("");
        if (wasWaiting) setNotice("A new code has been sent. The old one no longer works.");
      }
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function confirm(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      onSignedIn(await api.confirmEmail(email, code));
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  function switchTo(next: Mode) {
    setMode(next);
    setError(null);
    setNotice(null);
    setPending(null);
  }

  return (
    <div className="auth-page">
      <div className="auth-card panel">
        <Wordmark />
        <p className="tagline">Real people. Real economies. Real consequences.</p>

        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={mode === "login"} className={mode === "login" ? "tab active" : "tab"} onClick={() => switchTo("login")}>
            Log in
          </button>
          <button role="tab" aria-selected={mode === "signup"} className={mode === "signup" ? "tab active" : "tab"} onClick={() => switchTo("signup")}>
            Create account
          </button>
        </div>

        {pending ? (
          <form onSubmit={confirm}>
            <h2 className="step-title">Check your email</h2>
            <p className="muted">
              We sent a 6-digit code to <span className="strong">{pending.email}</span>. Type it in to open your account.
              It works for 15 minutes.
            </p>
            {pending.code_shown_on_screen && (
              <p className="test-mode" role="note">
                Test mode: no email service is connected, so the code is shown here instead of being emailed.
                Your code is <span className="mono strong">{pending.code_shown_on_screen}</span>
              </p>
            )}
            <label>
              6-digit code
              <input
                className="mono code-input" type="text" inputMode="numeric" autoComplete="one-time-code" required
                pattern="[0-9]{6}" maxLength={6} value={code} autoFocus
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              />
              <span className="hint">No email? Check your spam folder. If you already have an account, log in instead.</span>
            </label>
            {notice && <p className="saved" role="status">{notice}</p>}
            {error && <p className="error" role="alert">{error}</p>}
            <button className="button-primary wide" type="submit" disabled={busy || code.length !== 6}>
              {busy ? "Please wait…" : "Open my account"}
            </button>
            <div className="step-actions">
              <button type="button" className="button-quiet" disabled={busy} onClick={submit}>Send a new code</button>
              <button type="button" className="button-quiet" disabled={busy} onClick={() => { setPending(null); setError(null); }}>
                Change my details
              </button>
            </div>
          </form>
        ) : (
        <form onSubmit={submit}>
          <label>
            Email
            <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            {mode === "signup" && <span className="hint">One account per email address. We send a code to it to confirm it is yours.</span>}
          </label>

          {mode === "signup" && (
            <label>
              Display name
              <input type="text" autoComplete="nickname" required minLength={3} maxLength={24} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
              <span className="hint">The name other players see. 3 to 24 letters and numbers.</span>
            </label>
          )}

          <label>
            Password
            <input
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
              minLength={mode === "signup" ? 10 : 1}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {mode === "signup" && <span className="hint">At least 10 characters.</span>}
          </label>

          {mode === "signup" && (
            <>
              <label>
                Date of birth
                <input type="date" autoComplete="bday" required value={dateOfBirth} onChange={(e) => setDateOfBirth(e.target.value)} />
                <span className="hint">You must be 18 or older. We check your age and do not keep your birthday.</span>
              </label>
              <div className="field">
                <span className="field-label">Profile picture</span>
                <IconChoice value={icon} onChange={setIcon} />
                <span className="hint">You can change it at any time.</span>
              </div>
            </>
          )}

          {error && <p className="error" role="alert">{error}</p>}

          <button className="button-primary wide" type="submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
          </button>
        </form>
        )}

        <div className="auth-footer">
          <MarketPill live={live} />
          {live && <span className="muted mono">{formatLagosTime(live.now)} Lagos</span>}
        </div>
      </div>
    </div>
  );
}
