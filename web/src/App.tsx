import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Player } from "./api";
import { Auth } from "./Auth";
import { AccountantRail, AccountantWork, AssetManagerRail, AssetManagerWork, BuildRail } from "./BuildDesk";
import { CareerRail, CareerWork } from "./Career";
import { CompaniesRail, CompaniesWork } from "./Companies";
import { CompanyRail, CompanyWork } from "./Company";
import { DeskRail, DeskWork } from "./Desk";
import {
  HeadRail, InvestmentBankerRail, InvestmentBankerWork, JournalistWork, LawyerWork, RiskManagerWork,
} from "./Desks2";
import { EmpireRail, EmpireWork } from "./Empire";
import { FirmRail, FirmWork } from "./Firm";
import { EconomyRail, EconomyWork } from "./Economy";
import { MarketRail, MarketWork } from "./Market";
import { NewsRail, NewsWork } from "./News";
import { PortfolioRail, PortfolioWork } from "./Portfolio";
import { PropertyRail, PropertyWork } from "./Property";
import { BorrowRail, BorrowWork } from "./Borrow";
import { useRoute } from "./hooks";
import { ProfileRail, ProfileWork } from "./Profile";
import { MoreWork, Panel, SearchWork, Shell } from "./Shell";
import { play, setSoundSettings, unlockOnFirstTouch } from "./sound";
import { RankRail, RankWork } from "./Rank";
import { MessagesRail, MessagesWork, partnerFrom } from "./Messages";
import { WorkFocus, WorkRail, WorkWork } from "./Work";
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

  // The dot under the profile picture (a rank case, unread messages) is kept fresh.
  useEffect(() => {
    if (!player) return;
    const timer = window.setInterval(refreshPlayer, 60_000);
    return () => window.clearInterval(timer);
  }, [player === null || player === undefined, refreshPlayer]); // eslint-disable-line react-hooks/exhaustive-deps

  // The player's own look and sound follow them to every device.
  useEffect(() => { unlockOnFirstTouch(); }, []);
  const theme = player ? player.theme : "dark";
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  useEffect(() => { if (player) setSoundSettings(player.sound_on, player.sound_volume); }, [player]);
  // Sounds for what happens to the player while they are here: a new message, and a rank case or a
  // decision that has just started waiting. (Trades sound where they are placed; the bell in the shell.)
  const seen = useRef<{ unread: number; waiting: number; rank: boolean } | null>(null);
  useEffect(() => {
    if (!player) { seen.current = null; return; }
    const now = { unread: player.unread_messages, waiting: player.empire?.waiting ?? 0, rank: player.rank_waiting };
    const before = seen.current;
    if (before) {
      if (now.unread > before.unread) play("message");
      else if (now.waiting > before.waiting || (now.rank && !before.rank)) play("decision");
    }
    seen.current = now;
  }, [player]);

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
  let accent: string | undefined;
  let wide = false;

  if (section === "companies" && item) {
    current = "companies";
    work = <CompanyWork key={item} ticker={item} onLoggedOut={loggedOut} onTraded={refreshPlayer} />;
    rail = <CompanyRail key={item} ticker={item} onLoggedOut={loggedOut} onTraded={refreshPlayer} />;
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
    rail = <PortfolioRail onLoggedOut={loggedOut} />;
  } else if (section === "news") {
    current = "news";
    work = <NewsWork onLoggedOut={loggedOut} />;
    rail = <NewsRail />;
  } else if (section === "borrow") {
    current = "borrow";
    work = <BorrowWork key={item ?? ""} player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <BorrowRail onLoggedOut={loggedOut} />;
  } else if (section === "property") {
    current = "property";
    work = <PropertyWork key={item ?? ""} player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <PropertyRail onLoggedOut={loggedOut} />;
  } else if (section === "economy") {
    current = "economy";
    work = <EconomyWork onLoggedOut={loggedOut} />;
    rail = <EconomyRail onLoggedOut={loggedOut} />;
  } else if (section === "build" && player.build === "asset_manager") {
    current = "build";
    work = <AssetManagerWork player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <AssetManagerRail player={player} onLoggedOut={loggedOut} />;
  } else if (section === "build" && player.build === "accountant") {
    current = "build";
    work = <AccountantWork player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <AccountantRail player={player} onLoggedOut={loggedOut} />;
  } else if (section === "build" && player.build === "investment_banker") {
    current = "build";
    work = <InvestmentBankerWork player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <InvestmentBankerRail player={player} onLoggedOut={loggedOut} />;
  } else if (section === "build" && player.build === "risk_manager") {
    current = "build";
    work = <RiskManagerWork player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <BuildRail player={player} onLoggedOut={loggedOut} />;
  } else if (section === "build" && player.build === "lawyer") {
    current = "build";
    work = <LawyerWork player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <BuildRail player={player} onLoggedOut={loggedOut} />;
  } else if (section === "build" && player.build === "journalist") {
    current = "build";
    work = <JournalistWork player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <BuildRail player={player} onLoggedOut={loggedOut} />;
  } else if ((section === "empire" || section === "head" || section === "firm") && player.empire && !player.empire.forming) {
    // One section with tabs: the old addresses (#/head, #/firm) open its Overview and Desks tabs.
    current = "empire";
    accent = "neutral";
    const tab = section === "head" ? "overview" : section === "firm" ? (item ?? "desks") : item;
    work = <FirmWork key={tab ?? ""} player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} initialTab={tab} />;
    rail = tab === "overview" || !tab
      ? <HeadRail player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />
      : tab === "warroom" ? <EmpireRail player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />
      : <FirmRail player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
  } else if (section === "empire" || section === "head" || section === "firm") {
    current = "empire";
    accent = "neutral";
    work = <EmpireWork player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <EmpireRail player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
  } else if (section === "work" && item && /^\d+$/.test(item)) {
    current = "work";
    work = <WorkFocus key={item} id={Number(item)} player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} onPlayer={setPlayer} />;
    rail = <></>;
    wide = true;
  } else if (section === "work") {
    current = "work";
    work = <WorkWork player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <WorkRail player={player} onLoggedOut={loggedOut} />;
  } else if (section === "rank") {
    current = "rank";
    work = <RankWork player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <RankRail player={player} onLoggedOut={loggedOut} />;
  } else if (section === "career" || (section === "build" && !player.build)) {
    current = "career";
    work = <CareerWork player={player} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <CareerRail player={player} onLoggedOut={loggedOut} />;
  } else if (section === "more") {
    current = "more";
    work = <MoreWork player={player} onPlayer={setPlayer} onLogout={logout} />;
    rail = <></>;
  } else if (section === "search") {
    current = "search";
    work = <SearchWork player={player} />;
    rail = <></>;
  } else if (section === "messages") {
    current = "messages";
    const other = partnerFrom(item);
    work = <MessagesWork key={other ?? ""} with={other} onLoggedOut={loggedOut} onChanged={refreshPlayer} />;
    rail = <MessagesRail />;
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

  return <Shell player={player} live={live} current={current} onLogout={logout} onPlayer={setPlayer} wide={wide} work={work} rail={rail} accent={accent} />;
}
