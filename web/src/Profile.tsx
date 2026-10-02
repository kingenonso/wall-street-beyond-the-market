import { useState } from "react";
import { api, ApiError, type Player, type ProfileIcon } from "./api";
import { IconChoice } from "./Auth";
import { ProfilePicture } from "./icons";
import { Panel } from "./Shell";

export function ProfileWork({ player, onChanged }: { player: Player; onChanged: (player: Player) => void }) {
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function choose(icon: ProfileIcon) {
    setError(null);
    setSaved(false);
    try {
      onChanged(await api.setProfileIcon(icon));
      setSaved(true);
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again.");
    }
  }

  return (
    <>
      <div className="work-head">
        <h1>Your profile picture</h1>
        <span className="muted small">How other players will see you</span>
      </div>
      <Panel>
        <IconChoice value={player.profile_icon} onChange={choose} />
        {saved && <p className="saved" role="status">Saved.</p>}
        {error && <p className="error" role="alert">{error}</p>}
        <p className="muted small">
          Uploading a picture of your own arrives in a later stage, once pictures can be checked before other players see them.
          Your picture gives no advantage in the game.
        </p>
      </Panel>
    </>
  );
}

export function ProfileRail({ player }: { player: Player }) {
  return (
    <Panel title="How you will appear">
      <div className="identity">
        <ProfilePicture icon={player.profile_icon} name={player.display_name} size={48} />
        <div>
          <div className="strong">{player.display_name}</div>
          <div className="muted small">Reputation {player.reputation} of 100</div>
        </div>
      </div>
    </Panel>
  );
}
