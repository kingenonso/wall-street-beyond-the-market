import { useCallback, useEffect, useState } from "react";
import { api, type Player } from "./api";
import { Auth } from "./Auth";
import { CompaniesRail, CompaniesWork } from "./Companies";
import { CompanyRail, CompanyWork } from "./Company";
import { DeskRail, DeskWork } from "./Desk";
import { EconomyRail, EconomyWork } from "./Economy";
import { MarketRail, MarketWork } from "./Market";
import { NewsRail, NewsWork } from "./News";
import { PortfolioRail, PortfolioWork } from "./Portfolio";
import { useRoute } from "./hooks";
import { ProfileRail, ProfileWork } from "./Profile";
import { Panel, Shell } from "./Shell";
import { useClock } from "./useClock";

export function App() {
  // undefined = still checking, null = not logged in.
  const [player, setPlayer] = useState<Player | null | undefined>(undefined);
  const live = useClock();
  const route = useRoute();

  useEffect(() => {
    api.me().then(setPlayer).catch(() => setPlayer(null));
  }, []);

  const loggedOut = useCallback(() => setPlayer(null), []);
  // After a trade, the cash shown in the top bar is read again.
  const refreshPlayer = useCallback(() => { api.me().then(setPlayer).catch(() => undefined); }, []);

  async function logout() {
    await api.logout().catch(() => undefined);
    window.location.hash = "#/";
    setPlayer(null);
  }

  if (player === undefined) return <div className="loading">Loading…</div>;
  if (player === null) return <Auth live={live} onSignedIn={setPlayer} />;

  const [section = "", item] = route;
  let work = <DeskWork player={player} live={live} onLoggedOut={loggedOut} />;
  let rail = <DeskRail player={player} live={live} onLoggedOut={loggedOut} />;
  let current = "";

  if (section === "companies" && item) {
    current = "companies";
    work = <CompanyWork key={item} ticker={item} onLoggedOut={loggedOut} onTraded={refreshPlayer} />;
    rail = <CompanyRail key={item} ticker={item} onLoggedOut={loggedOut} />;
  } else if (section === "companies") {
    current = "companies";
    work = <CompaniesWork onLoggedOut={loggedOut} />;
    rail = <CompaniesRail />;
  } else if (section === "market") {
    current = "market";
    work = <MarketWork key={item ?? ""} tab={item ?? ""} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <MarketRail onLoggedOut={loggedOut} />;
  } else if (section === "portfolio") {
    current = "portfolio";
    work = <PortfolioWork onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <PortfolioRail />;
  } else if (section === "news") {
    current = "news";
    work = <NewsWork onLoggedOut={loggedOut} />;
    rail = <NewsRail />;
  } else if (section === "economy") {
    current = "economy";
    work = <EconomyWork onLoggedOut={loggedOut} />;
    rail = <EconomyRail onLoggedOut={loggedOut} />;
  } else if (section === "profile") {
    current = "profile";
    work = <ProfileWork player={player} onChanged={setPlayer} />;
    rail = <ProfileRail player={player} />;
  } else if (section !== "") {
    work = (
      <Panel title="There is nothing at this address">
        <p className="muted">Go back to <a href="#/">your desk</a>.</p>
      </Panel>
    );
    rail = <></>;
  }

  return <Shell player={player} live={live} current={current} onLogout={logout} work={work} rail={rail} />;
}
