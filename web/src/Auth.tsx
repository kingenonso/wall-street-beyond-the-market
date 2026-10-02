import { useState, type FormEvent } from "react";
import { api, ApiError, type Player, type ProfileIcon } from "./api";
import { formatLagosTime } from "./format";
import { ProfilePicture } from "./icons";
import { MarketPill, Wordmark } from "./Shell";
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

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (mode === "signup" && icon === null) {
      setError("Choose a profile picture: the male icon or the female icon.");
      return;
    }
    setBusy(true);
    try {
      const player =
        mode === "login"
          ? await api.login(email, password)
          : await api.signup({ email, display_name: displayName, password, date_of_birth: dateOfBirth, profile_icon: icon! });
      onSignedIn(player);
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  function switchTo(next: Mode) {
    setMode(next);
    setError(null);
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

        <form onSubmit={submit}>
          <label>
            Email
            <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>

          {mode === "signup" && (
            <label>
              Display name
              <input type="text" autoComplete="nickname" required minLength={3} maxLength={24} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
              <span className="hint">The name other players see. 3 to 24 characters.</span>
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

        <div className="auth-footer">
          <MarketPill live={live} />
          {live && <span className="muted mono">{formatLagosTime(live.now)} Lagos</span>}
        </div>
      </div>
    </div>
  );
}
