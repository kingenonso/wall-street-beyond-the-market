import { useState } from "react";
import { ApiError, api, type ArchiveItem, type Fact, type NewsItem, type NewsroomDesk, type Player, type PlayerStory, type WhyChain } from "./api";
import { useLoad } from "./hooks";
import { Failed, Loading, Panel } from "./Shell";
import { Term } from "./Term";

/** Stage 10: one action on the newsroom's server routes, with its message. */
export function useRun(reload: () => void, onLoggedOut: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function run(call: () => Promise<{ result: unknown }>, done: string | ((r: Record<string, unknown>) => string)) {
    setBusy(true); setError(null); setNotice(null);
    try {
      const answer = await call();
      const result = (answer?.result ?? {}) as Record<string, unknown>;
      setNotice(typeof done === "string" ? done : done(result));
      reload();
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) return onLoggedOut();
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, notice, run };
}
export type Run = ReturnType<typeof useRun>;

export function Notices({ act }: { act: Run }) {
  return (
    <>
      {act.notice && <p className="notice" role="status">{act.notice}</p>}
      {act.error && <p className="error" role="alert">{act.error}</p>}
    </>
  );
}

/** "Why?": the chain of causes behind something, at three depths. */
export function Why({ keyName }: { keyName: string }) {
  const [depth, setDepth] = useState<0 | 1 | 2 | 3>(0);
  const [chain, setChain] = useState<WhyChain | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  async function open(next: 1 | 2 | 3) {
    setDepth(next);
    if (!chain) {
      try { setChain(await api.whyChain(keyName)); } catch (problem) { setFailed(problem instanceof ApiError ? problem.message : "Could not reach the server."); }
    }
  }
  return (
    <div className="why-box">
      <div className="button-row" role="group" aria-label="Why, at three depths">
        <span className="small strong"><Term word="The Ripple">Why?</Term></span>
        <button className="filter-chip" aria-pressed={depth === 1} onClick={() => open(1)}>In one line</button>
        <button className="filter-chip" aria-pressed={depth === 2} onClick={() => open(2)}>The full chain</button>
        <button className="filter-chip" aria-pressed={depth === 3} onClick={() => open(3)}>The numbers</button>
      </div>
      {failed && <p className="error small">{failed}</p>}
      {chain && depth === 1 && <p className="small">{chain.one_line}</p>}
      {chain && depth === 2 && (chain.chain.length ? <ol className="reasons small">{chain.chain.map((c, i) => <li key={i}>{c}</li>)}</ol>
        : <p className="muted small">No cause is on the record for this yet.</p>)}
      {chain && depth === 3 && (chain.numbers.length ? (
        <ul className="reasons small">{chain.numbers.map((n, i) => (
          <li key={i}>{n.step} <span className="mono muted">{Object.entries(n.figures).map(([k, v]) => `${k}: ${v}`).join(" · ")}</span></li>
        ))}</ul>) : <p className="muted small">No figures are on the record for this chain.</p>)}
    </div>
  );
}

/** The full article behind a wire item, the earlier items it follows up, and "Why?". */
export function ArticleBelow({ item }: { item: NewsItem }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Awaited<ReturnType<typeof api.article>> | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  if (!item.ref) return null;
  async function show() {
    setOpen(!open);
    if (!data && item.ref) {
      try { setData(await api.article(item.ref)); } catch (problem) { setFailed(problem instanceof ApiError ? problem.message : "Could not reach the server."); }
    }
  }
  return (
    <div className="article-below">
      <button className="button-quiet" aria-expanded={open} onClick={show}>{open ? "Close the article" : item.author ? "More on this story" : "Read the full article"}</button>
      {open && failed && <p className="error small">{failed}</p>}
      {open && data && (
        <div className="article-text">
          {data.article ? data.article.body.split("\n\n").map((p, i) => <p key={i}>{p}</p>)
            : !item.author && <p className="muted small">Today's twenty full articles have been written. The wire item above stands on its own until tomorrow.</p>}
          {data.article && <p className="muted small">{data.article.writer === "service" ? "Written by the news service" : "A wire report"}: written from the recorded facts; every figure was checked against the record.</p>}
          {data.thread.length > 1 && (
            <div>
              <div className="lbl">This story so far</div>
              <ul className="reasons small">{data.thread.map((t, i) => <li key={i}>{t.label}, day {t.day}: {t.headline}{t.this ? " (this item)" : ""}</li>)}</ul>
            </div>
          )}
          {data.why && <Why keyName={data.why} />}
        </div>
      )}
    </div>
  );
}

/** Players' published stories. */
export function PlayersStories({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [author, setAuthor] = useState<string | null>(null);
  const { data, error, loading, reload } = useLoad(() => api.stories(author ?? undefined), `stories:${author ?? ""}`, onLoggedOut);
  const act = useRun(reload, onLoggedOut);
  if (loading && !data) return <Loading what="players' stories" />;
  if (error) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  return (
    <>
      <Notices act={act} />
      {author && data.profile && (
        <Panel title={`${author}: a journalist's record`} aside={<button className="button-quiet" onClick={() => setAuthor(null)}>All stories</button>}>
          <div className="stat-row">
            {STATS.map(([k, label]) => <div key={k}><div className="lbl">{label}</div><div className="mono figure-small">{data.profile![k].toLocaleString("en-NG")}</div></div>)}
          </div>
        </Panel>
      )}
      {data.stories.length === 0 && <Panel><p className="muted">No player has published a story yet. Financial Journalists write them from confirmed facts.</p></Panel>}
      <div className="stories">
        {data.stories.map((s: PlayerStory) => (
          <article key={s.id} className="story">
            <div className="story-top">
              <span className="card-tag">{s.outlet}{s.scoop ? " · Scoop" : ""}{s.corrected ? " · Corrected" : ""}</span>
              <span className="mono muted">{s.label}, day {s.day}</span>
            </div>
            <h2 className="h3-look">{s.headline}</h2>
            <p className="muted">{s.body}</p>
            <div className="button-row">
              <span className="small muted">By <button className="link-button" onClick={() => setAuthor(s.author)}>{s.author}</button> · {s.readers.toLocaleString("en-NG")} readers</span>
              <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.post(`/stories/${s.id}/expose`), (r) => String(r.words ?? "Done."))}>
                Raise an undeclared interest
              </button>
            </div>
            <Why keyName={`story:${s.id}`} />
          </article>
        ))}
      </div>
    </>
  );
}

/** Every story ever published, searchable. */
export function Archive({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [q, setQ] = useState("");
  const [ticker, setTicker] = useState("");
  const [asked, setAsked] = useState<{ q: string; ticker: string }>({ q: "", ticker: "" });
  const { data, error, loading, reload } = useLoad(() => api.archive(asked.q || undefined, asked.ticker || undefined), `archive:${asked.q}:${asked.ticker}`, onLoggedOut);
  return (
    <>
      <Panel title="Search the archive" aside="every story ever published">
        <form className="form-grid" onSubmit={(e) => { e.preventDefault(); setAsked({ q: q.trim(), ticker: ticker.trim().toUpperCase() }); }}>
          <label className="answer">Words<input type="search" maxLength={60} value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. flood, rate, Danfo" /></label>
          <label className="answer">Company ticker<input type="text" maxLength={5} value={ticker} onChange={(e) => setTicker(e.target.value)} placeholder="e.g. IDC" /></label>
          <button className="button-outline">Search</button>
        </form>
      </Panel>
      {loading && !data && <Loading what="the archive" />}
      {error && <Failed message={error} onRetry={reload} />}
      {data && (
        <Panel title={`${data.items.length} ${data.items.length === 1 ? "story" : "stories"}`}>
          {data.items.length === 0 && <p className="muted">Nothing found.</p>}
          {data.items.map((i: ArchiveItem) => (
            <div key={i.ref} className="archive-row">
              <div className="small muted">{i.label}, day {i.day} · {i.outlet}{i.author ? ` · by ${i.author}` : ""}{i.follows_up ? " · a follow-up" : ""}</div>
              <div className="strong">{i.headline}</div>
              <p className="small muted">{i.body}</p>
            </div>
          ))}
        </Panel>
      )}
    </>
  );
}

/** The Chronicle: the world's memory, in three layers. */
export function Chronicle({ player, onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  const [layer, setLayer] = useState<"world" | "company" | "personal">("world");
  const { data, error, loading, reload } = useLoad(() => api.chronicle(layer), `chronicle:${layer}`, onLoggedOut);
  const mine = useLoad(() => (player.build === "investment_banker" ? api.newsroom() : Promise.resolve(null)), "chronicle-mine", onLoggedOut);
  const act = useRun(reload, onLoggedOut);
  const [writing, setWriting] = useState<number | null>(null);
  const [words, setWords] = useState("");
  const [evidence, setEvidence] = useState<number[]>([]);
  return (
    <>
      <div className="filter-row" role="group" aria-label="Which layer">
        {(["world", "company", "personal"] as const).map((l) => (
          <button key={l} className="filter-chip" aria-pressed={layer === l} onClick={() => setLayer(l)}>{l === "world" ? "The world" : l === "company" ? "Companies" : "My own story"}</button>
        ))}
      </div>
      <p className="muted small"><Term word="The Chronicle">The Chronicle</Term> keeps what happened, for good. The game writes the record; journalists add signed accounts beside it.</p>
      <Notices act={act} />
      {loading && !data && <Loading what="the Chronicle" />}
      {error && <Failed message={error} onRetry={reload} />}
      {data && data.entries.length === 0 && <Panel><p className="muted">Nothing here yet. Entries are written as things happen and at each quarter's close.</p></Panel>}
      {data && data.entries.map((e) => (
        <Panel key={e.id} title={e.title} aside={`${e.label}, day ${e.day}`}>
          <p>{e.words}</p>
          {e.accounts.map((a, i) => (
            <blockquote key={i} className="account">
              <p className="small">{a.words}</p>
              <div className="small muted">{a.author} · credibility {a.credibility} · {a.evidence.length} {a.evidence.length === 1 ? "story" : "stories"} cited</div>
            </blockquote>
          ))}
          {layer !== "personal" && <Why keyName={e.ref} />}
          {layer !== "personal" && player.build === "investment_banker" && (writing === e.id ? (
            <form className="stack-form" onSubmit={(ev) => { ev.preventDefault(); act.run(() => api.post(`/chronicle/${e.id}/accounts`, { words, evidence }), (r) => `Your account is in the Chronicle, with credibility ${r.credibility}.`); setWriting(null); }}>
              <label className="answer">Your account (40 to 1,200 characters)<textarea maxLength={1200} rows={4} value={words} onChange={(ev) => setWords(ev.target.value)} /></label>
              <fieldset className="small"><legend>Evidence: your own published stories</legend>
                {(mine.data?.desk.published ?? []).map((s) => (
                  <label key={s.id} className="check-line"><input type="checkbox" checked={evidence.includes(s.id)}
                    onChange={(ev) => setEvidence(ev.target.checked ? [...evidence, s.id].slice(0, 5) : evidence.filter((x) => x !== s.id))} /> {s.headline}</label>
                ))}
              </fieldset>
              <div className="button-row"><button className="button-outline" disabled={act.busy || words.trim().length < 40}>Add your account</button>
                <button type="button" className="button-quiet" onClick={() => setWriting(null)}>Cancel</button></div>
            </form>
          ) : <button className="button-quiet" onClick={() => { setWriting(e.id); setWords(""); setEvidence([]); }}>Write an account of this</button>)}
        </Panel>
      ))}
    </>
  );
}

/** Questions from journalists waiting on the head of an empire. */
export function PressQuestions({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.pressQuestions, "press-questions", onLoggedOut);
  const act = useRun(reload, onLoggedOut);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  if (loading && !data) return <Loading what="the press's questions" />;
  if (error) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  return (
    <>
      <Notices act={act} />
      {data.questions.length === 0 && <Panel><p className="muted">No journalist is waiting on you.</p></Panel>}
      {data.questions.map((q) => (
        <Panel key={q.id} title={`${q.journalist} asks ${q.empire}`} aside={`answer by ${new Date(q.due_at).toLocaleString("en-NG", { timeZone: "Africa/Lagos", dateStyle: "medium", timeStyle: "short" })}`}>
          <p>“{q.question}”</p>
          <label className="answer answer-block">Your answer, on the record (300 characters)<textarea rows={3} maxLength={300} value={answers[q.id] ?? ""} onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} /></label>
          <div className="button-row">
            <button className="button-outline" disabled={act.busy || !(answers[q.id] ?? "").trim()} onClick={() => act.run(() => api.post(`/interviews/${q.id}/answer`, { words: answers[q.id] }), "Answered on the record.")}>Answer</button>
            <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.post(`/interviews/${q.id}/answer`, { words: null }), "Declined to comment.")}>Decline to comment</button>
          </div>
          <p className="muted small">Answering on the record raises your empire's good name a little; letting the question run out of time lowers it.</p>
        </Panel>
      ))}
    </>
  );
}

const STATS: [keyof NewsroomDesk["profile"], string][] = [["readers", "Readers"], ["following", "Following"], ["stories", "Stories"], ["scoops", "Scoops"], ["corrections", "Corrections"], ["credibility", "Credibility"]];

/** The journalist's newsroom: write a story from confirmed facts, check each one, ask for comment, publish. */
export function NewsroomDeskView({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.newsroom, "newsroom", onLoggedOut);
  const [ticker, setTicker] = useState("");
  const [kind, setKind] = useState("all");
  const [showAll, setShowAll] = useState(false);
  const facts = useLoad(() => api.newsroomFacts(ticker || undefined), `facts:${ticker}`, onLoggedOut);
  const act = useRun(() => { reload(); facts.reload(); }, onLoggedOut);
  const [angle, setAngle] = useState<string | null>(null);
  const [comment, setComment] = useState<string | null>(null);
  const [declared, setDeclared] = useState<boolean | null>(null);
  const [askWho, setAskWho] = useState<"company" | "empire">("company");
  const [askName, setAskName] = useState("");
  const [question, setQuestion] = useState("");
  if (loading && !data) return <Loading what="the newsroom" />;
  if (error) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  const d = data.desk;
  const draft = d.draft;
  const chosen = new Set((draft?.facts ?? []).map((f) => f.id));
  const allChecked = !!draft && (draft.facts.length > 0 || !!draft.lead) && draft.facts.every((f) => f.checked);
  return (
    <>
      <Panel title="Your newsroom" aside={`writing for ${d.writing_for}${d.empire ? ` · you sit in ${d.empire}` : ""}`}>
        <div className="stat-row">
          {STATS.map(([k, label]) => (
            <div key={k}><div className="lbl">{k === "credibility" ? <Term word="Credibility">{label}</Term> : k === "scoops" ? <Term word="Scoop">{label}</Term> : label}</div>
              <div className="mono figure-small">{d.profile[k].toLocaleString("en-NG")}</div></div>
          ))}
        </div>
        <p className="muted small">Readers depend on how big the news is, how early it is, your paper's audience and your name. Pay rises with your following.</p>
      </Panel>
      <Notices act={act} />
      {d.to_correct.length > 0 && (
        <Panel title="Corrections due" className="panel-warn">
          {d.to_correct.map((s) => (
            <div key={s.id} className="row">
              <span>{s.headline}{s.late ? " (late)" : ""}</span>
              <button className="button-outline" disabled={act.busy} onClick={() => act.run(() => api.post(`/newsroom/stories/${s.id}/correct`), "Correction published.")}>Publish the correction</button>
            </div>
          ))}
          <p className="muted small">The record changed after you published. Correct within a day: a correction costs 3 reputation, a late one 6 and a tenth of your following.</p>
        </Panel>
      )}
      {!draft ? (
        <Panel title="Write a story">
          <p className="muted small">A story is built from confirmed facts on the record. You choose them, check each against where it is kept, may ask for comment, add your own view in words, and publish.</p>
          <button className="button-primary" disabled={act.busy} onClick={() => act.run(() => api.post("/newsroom/story"), "A new story is open.")}>Start a story</button>
        </Panel>
      ) : (
        <Panel title="Your story in hand" aside={draft.tickers.length ? `No trading ${draft.tickers.join(", ")} by you or your empire until two trading days after it runs` : undefined}>
          {draft.facts.length === 0 && !draft.lead && <p className="muted">Choose one to five facts from the list below, or put in a piece you hold (Intelligence).</p>}
          {draft.lead && (
            <div className="fact-row">
              <div>
                <div className="strong">Unconfirmed report</div>
                <div className="small">{draft.lead.words}</div>
                <div className="small muted">Printed as unconfirmed unless the record has borne it out. What readers believe is kept against what turns out to be true.</div>
              </div>
              <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.post("/newsroom/lead/remove"), "Taken out.")}>Take out</button>
            </div>
          )}
          {d.titles.length > 0 && (
            <label className="answer">Where it runs<select value={draft.title_id ?? ""} onChange={(e) => act.run(() => api.post("/newsroom/title", { title_id: e.target.value ? Number(e.target.value) : null }), "Saved.")}>
              <option value="">{d.writing_for === "Independent" ? "as an independent" : d.writing_for}</option>
              {d.titles.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.audience.toLocaleString("en-NG")} readers)</option>)}
            </select></label>
          )}
          {draft.facts.map((f) => (
            <div key={f.id} className="fact-row">
              <div>
                <div className="strong">{f.title}</div>
                <div className="small">{f.line}</div>
                <div className="small muted">Kept in: {f.record}</div>
              </div>
              <div className="button-row">
                {f.checked ? <span className="tag-good small">✓ Checked</span>
                  : <button className="button-outline" disabled={act.busy} onClick={() => act.run(() => api.post("/newsroom/check", { fact_id: f.id }), (r) => String(r.words ?? "Checked."))}>Check it</button>}
                <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.post("/newsroom/facts/remove", { fact_id: f.id }), "Taken out.")}>Take out</button>
              </div>
            </div>
          ))}
          <form className="form-grid" onSubmit={(e) => { e.preventDefault(); act.run(() => api.newsroomWords({ angle: angle ?? draft.angle, comment: comment ?? draft.comment, declared: declared ?? draft.declared }), "Saved."); }}>
            <label className="answer">How it is told<select value={angle ?? draft.angle} onChange={(e) => setAngle(e.target.value)}>
              {Object.entries(d.angles).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            <label className="answer">Your own view, in words (no figures)<input type="text" maxLength={280} value={comment ?? draft.comment} onChange={(e) => setComment(e.target.value)} /></label>
            {d.empire && <label className="check-line"><input type="checkbox" checked={declared ?? draft.declared} onChange={(e) => setDeclared(e.target.checked)} /> <Term word="Declared interest">Declare</Term> {d.empire}'s interest</label>}
            <button className="button-quiet" disabled={act.busy}>Save</button>
          </form>
          <div>
            <div className="lbl">Ask for comment</div>
            {draft.interviews.map((i) => (
              <div key={i.id} className="small"><span className="strong">{i.who}</span>: “{i.question}” — {i.status === "asked" ? "waiting for an answer" : i.answer ?? i.status}</div>
            ))}
            <form className="form-grid" onSubmit={(e) => { e.preventDefault(); act.run(() => api.post("/newsroom/ask", askWho === "company" ? { ticker: askName.trim().toUpperCase(), question } : { empire: askName.trim(), question }), "Asked."); setQuestion(""); }}>
              <label className="answer">Ask<select value={askWho} onChange={(e) => setAskWho(e.target.value as "company" | "empire")}><option value="company">a company</option><option value="empire">an empire's head</option></select></label>
              <label className="answer">{askWho === "company" ? "Ticker" : "Empire's name"}<input type="text" maxLength={40} value={askName} onChange={(e) => setAskName(e.target.value)} /></label>
              <label className="answer">Question<input type="text" maxLength={300} value={question} onChange={(e) => setQuestion(e.target.value)} /></label>
              <button className="button-quiet" disabled={act.busy || question.trim().length < 10 || !askName.trim()}>Ask</button>
            </form>
          </div>
          <div className="button-row">
            <button className="button-primary" disabled={act.busy || !allChecked} onClick={() => act.run(() => api.post("/newsroom/publish"),
              (r) => `Published: ${Number(r.readers ?? 0).toLocaleString("en-NG")} readers${r.scoop ? ", a scoop" : ""}.`)}>Publish</button>
            <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.post("/newsroom/drop"), "Dropped.")}>Drop the story</button>
            {!allChecked && draft.facts.length > 0 && <span className="muted small">Check every fact before it goes to print.</span>}
          </div>
        </Panel>
      )}
      <Panel title="Confirmed facts on the record today" aside="only what is public and has already happened">
        <label className="answer small">Only about a company<input type="text" maxLength={5} value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} placeholder="ticker" /></label>
        {facts.loading && !facts.data && <Loading what="the facts" />}
        {facts.data && (
          <div className="filter-row" role="group" aria-label="Kind of fact">
            {[["all", "All"], ["results", "Results"], ["rating", "Ratings"], ["takeover", "Takeovers"], ["stake", "Stakes"], ["rate", "The rate"],
              ["event", "Events"], ["price", "Share prices"], ["infrastructure", "Public works"], ["homes", "Homes"]]
              .filter(([k]) => k === "all" || facts.data!.facts.some((f: Fact) => f.kind === k))
              .map(([k, label]) => (
                <button key={k} className="filter-chip" aria-pressed={kind === k} onClick={() => { setKind(k); setShowAll(false); }}>{label}</button>
              ))}
          </div>
        )}
        {facts.data && facts.data.facts.filter((f: Fact) => kind === "all" || f.kind === kind).slice(0, showAll ? undefined : 12).map((f: Fact) => (
          <div key={f.id} className="fact-row">
            <div><div className="strong">{f.title} {f.tone > 0 ? <span className="tag-good small">good news</span> : f.tone < 0 ? <span className="tag-bad small">bad news</span> : null}</div>
              <div className="small muted">{f.line}</div></div>
            <button className="button-quiet" disabled={act.busy || !draft || chosen.has(f.id)} onClick={() => act.run(() => api.post("/newsroom/facts", { fact_id: f.id }), "Added to your story.")}>
              {chosen.has(f.id) ? "In your story" : "Use it"}</button>
          </div>
        ))}
        {facts.data && !showAll && facts.data.facts.filter((f: Fact) => kind === "all" || f.kind === kind).length > 12 && (
          <button className="button-quiet" onClick={() => setShowAll(true)}>
            Show all {facts.data.facts.filter((f: Fact) => kind === "all" || f.kind === kind).length} facts</button>
        )}
      </Panel>
      <Panel title="Your editors" aside="they remember how your work for them went">
        {d.editors.map((e) => (
          <div key={e.client} className="row"><span><span className="strong">{e.name}</span>, {e.role}</span><span className="mono">trust {e.trust}{e.offering ? "" : " · no work for now"}</span></div>
        ))}
        <p className="muted small">Work for an editor appears on your Work page. Done well, their trust rises; done badly, it falls twice as fast. Below 30 they stop offering work; at 70 they offer the front page.</p>
      </Panel>
      {d.published.length > 0 && (
        <Panel title="Your published stories">
          {d.published.map((s) => (
            <div key={s.id} className="row"><span>{s.headline}{s.scoop ? " · scoop" : ""}{s.corrected ? " · corrected" : ""}</span><span className="mono">{s.readers.toLocaleString("en-NG")} readers</span></div>
          ))}
        </Panel>
      )}
    </>
  );
}
