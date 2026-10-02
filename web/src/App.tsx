import { useEffect, useState } from "react";
import { api, type Player } from "./api";
import { Auth } from "./Auth";
import { Home } from "./Home";
import { TopBar } from "./TopBar";
import { useClock } from "./useClock";

export function App() {
  // undefined = still checking, null = not logged in.
  const [player, setPlayer] = useState<Player | null | undefined>(undefined);
  const live = useClock();

  useEffect(() => {
    api.me().then(setPlayer).catch(() => setPlayer(null));
  }, []);

  async function logout() {
    await api.logout().catch(() => undefined);
    setPlayer(null);
  }

  if (player === undefined) return <div className="loading">Loading…</div>;
  if (player === null) return <Auth live={live} onSignedIn={setPlayer} />;
  return (
    <>
      <TopBar player={player} live={live} onLogout={logout} />
      <Home player={player} live={live} />
    </>
  );
}
