"use client";

import { useEffect, useState } from "react";
import { Archive, ArrowDown, ArrowUp, ArrowUpRight, Bookmark, Check, CheckCheck, Search, Settings } from "lucide-react";
import { briefingStories, dateInZone, emptyReaderState, parseReaderState, sectorStories, type EditionData, type EditionStory, type EditionView, type ReaderState } from "@/lib/edition";
import { SportsSection } from "./sports-section";
import { ThemePicker } from "./theme-picker";

const storageKey = "news4u-reader-v1";
const discoveryNames: Record<string, string> = { tldr_tech: "TLDR Tech", tldr_ai: "TLDR AI", hackernews: "Hacker News", techmeme: "Techmeme", alphasignal: "AlphaSignal" };
const sectors = ["Technology", "AI", "Markets", "Economy", "Deals & regulation", "World", "Policy", "Science & health", "Reading room", "Listening room", "Other", "Sports"];

function Picture({ story, small = false }: { story: EditionStory; small?: boolean }) {
  const [failed, setFailed] = useState(false);
  const [useOriginal, setUseOriginal] = useState(false);
  const [nativeWidth, setNativeWidth] = useState<number | null>(null);
  if (!story.image || failed) return null;
  // Publisher images are optional. Never substitute an unrelated stock photo.
  return <figure className={small ? "brief-photo" : "report-photo"} style={nativeWidth ? { maxWidth: nativeWidth } : undefined}>
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img src={(!useOriginal && story.imageAsset?.src) || story.image} width={story.imageAsset?.width} height={story.imageAsset?.height} alt="" loading="lazy" referrerPolicy="no-referrer" onLoad={e => { setNativeWidth(e.currentTarget.naturalWidth); if (e.currentTarget.naturalWidth < 400 || e.currentTarget.naturalHeight < 200) setFailed(true); }} onError={() => { if (story.imageAsset && !useOriginal) setUseOriginal(true); else setFailed(true); }} />
    {story.imageAsset ? <figcaption><a href={story.imageAsset.licenseUrl} target="_blank" rel="noreferrer">{story.imageAsset.credit}</a></figcaption> : !small && <figcaption>{story.publisher}</figcaption>}
  </figure>;
}


function ReportNotes({ story }: { story: EditionStory }) {
  return <div className="report-notes">
    {story.audioUrl && <div className="episode-audio"><p className="section-meta">{story.duration ? `${Math.round(story.duration / 60)} MIN / ` : ""}ORIGINAL EPISODE</p><audio controls preload="none" src={story.audioUrl}>Audio playback is unavailable. <a href={story.audioUrl}>Open audio</a></audio></div>}
    {story.contentBasis && <p className="notes-provenance">Editorial summary · {story.contentBasis}</p>}
    {!!story.points?.length && <section className="key-takeaways"><h3>{story.kind === "podcast" ? "The takeaways" : "What matters"}</h3><ul>{story.points.map((point, i) => <li key={i}>{point}</li>)}</ul></section>}
    {story.kind === "podcast" && !!story.sections?.length && <nav className="episode-contents" aria-label="Episode topics">{story.sections.map((section, i) => <a key={i} href={`#note-${i}`}><span>{String(i + 1).padStart(2, "0")}</span>{section.heading}</a>)}</nav>}
    {story.sections?.map((section, i) => <section className="note-section" id={`note-${i}`} key={i}><h3>{section.heading}</h3>{section.body.split(/\n\n+/).map((paragraph, j) => <p key={j}>{paragraph}</p>)}</section>)}
    {!!story.caveats?.length && <section className="note-section"><h3>Context & caveats</h3><ul>{story.caveats.map((caveat, i) => <li key={i}>{caveat}</li>)}</ul></section>}
    {story.editorialReason && <details className="editorial-reason"><summary>Why this made the edition</summary><p>{story.editorialReason}</p><a href={story.url} target="_blank" rel="noreferrer">Source material <ArrowUpRight /></a></details>}
  </div>;
}

export function NewsEdition({ edition, initialView = "Today", initialQuery = "", initialSector = "All sectors", initialStory = null, staticMode = false, archivedEdition = false }: { edition: EditionData; initialView?: EditionView; initialQuery?: string; initialSector?: string; initialStory?: string | null; staticMode?: boolean; archivedEdition?: boolean }) {
  const [view, setView] = useState<EditionView>(initialView);
  const [topic, setTopic] = useState(initialSector);
  const [query, setQuery] = useState(initialQuery);
  const [sort, setSort] = useState("editorial");
  const [reader, setReader] = useState<ReaderState>(emptyReaderState);
  const [ready, setReady] = useState(false);
  const [notice, setNotice] = useState("");
  const home = staticMode ? "./index.html" : "/";
  const reportHref = (s: EditionStory) => staticMode ? `${edition.stories.some(item => item.id === s.id) ? "./" : "/"}report-${encodeURIComponent(s.id)}.html` : `/story/${encodeURIComponent(s.id)}`;
  useEffect(() => {
    function load() {
      try { setReader(parseReaderState(JSON.parse(localStorage.getItem(storageKey) || "{}"))); } catch { setReader(emptyReaderState); }
      setReady(true);
    }
    load();
    const params = new URLSearchParams(location.search);
    const requestedView = params.get("view");
    if (["Today", "I do not have time", "Catch up", "Saved", "Archived", "Sources", "Settings"].includes(requestedView || "")) setView(requestedView as EditionView);
    window.addEventListener("storage", load);
    return () => window.removeEventListener("storage", load);
  }, [edition.stories]);
  useEffect(() => { if (!notice) return; const timer = setTimeout(() => setNotice(""), 3500); return () => clearTimeout(timer); }, [notice]);
  function update(next: ReaderState) {
    const known = new Map([...reader.library, ...edition.stories].map(s => [s.id, s]));
    next.library = [...new Set([...next.saved, ...next.archived])].flatMap(id => known.has(id) ? [known.get(id)!] : []);
    setReader(next);
    try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { setNotice("Browser storage is unavailable. Changes will last for this visit only."); }
  }
  function toggle(key: "saved" | "read" | "archived", id: string) {
    const enabled = !reader[key].includes(id);
    update({ ...reader, [key]: enabled ? [...reader[key], id] : reader[key].filter(value => value !== id) });
    setNotice(key === "saved" ? enabled ? "Story saved" : "Removed from saved" : key === "read" ? enabled ? "Marked read" : "Marked unread" : enabled ? "Story archived" : "Story restored");
  }
  const cutoff = Date.parse(edition.generatedAt) - edition.windowHours * 3600_000;
  const publishedIds = new Set(edition.stories.map(s => s.id));
  const available = [...edition.stories, ...reader.library.filter(s => !edition.stories.some(item => item.id === s.id))];
  const visible = available.filter(s => {
    if (["Today", "I do not have time"].includes(view) && !publishedIds.has(s.id)) return false;
    if (view === "Saved" && !reader.saved.includes(s.id)) return false;
    if (view === "Archived" ? !reader.archived.includes(s.id) : view !== "Saved" && reader.archived.includes(s.id)) return false;
    if (view === "Catch up" && (s.longform || reader.read.includes(s.id) || Date.parse(s.publishedAt) >= cutoff)) return false;
    if (!["Saved", "Archived"].includes(view) && reader.hiddenSources.includes(s.publisher)) return false;
    return (topic === "All sectors" || s.sector === topic) && `${s.title} ${s.summary} ${s.publisher}`.toLowerCase().includes(query.toLowerCase());
  });
  const topics = [...new Set([...sectors, ...available.map(s => s.sector)])].filter(s => available.some(story => story.sector === s) || (s === "Sports" && edition.sports));
  const groups = topics.map(name => ({ name, stories: sectorStories(visible.filter(s => s.sector === name), sort, reader.order) })).filter(g => g.stories.length || (g.name === "Sports" && edition.sports && view === "Today" && !query && ["All sectors", "Sports"].includes(topic)));
  const story = available.find(s => s.id === initialStory);
  const topStories = briefingStories(visible);
  function move(id: string, direction: number, items: EditionStory[]) {
    const ids = items.map(s => s.id), from = ids.indexOf(id), to = from + direction;
    if (to < 0 || to >= ids.length) return;
    [ids[from], ids[to]] = [ids[to], ids[from]];
    const other = groups.filter(g => g.name !== items[0].sector).flatMap(g => g.stories.map(s => s.id));
    update({ ...reader, order: [...ids, ...other, ...reader.order.filter(value => !ids.includes(value) && !other.includes(value))] });
    setSort("custom");
    setNotice("Story order updated within this sector");
  }
  function actions(s: EditionStory) {
    return <div className="story-actions">
      <button disabled={!ready} className="tool" title={reader.saved.includes(s.id) ? "Unsave story" : "Save story"} aria-label={reader.saved.includes(s.id) ? "Unsave story" : "Save story"} aria-pressed={reader.saved.includes(s.id)} onClick={() => toggle("saved", s.id)}><Bookmark /></button>
      <button disabled={!ready} className="tool" title={reader.read.includes(s.id) ? "Mark unread" : "Mark read"} aria-label={reader.read.includes(s.id) ? "Mark unread" : "Mark read"} aria-pressed={reader.read.includes(s.id)} onClick={() => toggle("read", s.id)}><Check /></button>
      <button disabled={!ready} className="tool" title={reader.archived.includes(s.id) ? "Restore story" : "Archive story"} aria-label={reader.archived.includes(s.id) ? "Restore story" : "Archive story"} aria-pressed={reader.archived.includes(s.id)} onClick={() => toggle("archived", s.id)}><Archive /></button>
    </div>;
  }
  function meta(s: EditionStory) { return <p className="byline">{s.publisher}{s.kind && s.kind !== "reporting" && <span> / {s.kind === "podcast" ? "Podcast" : s.kind === "announcement" ? "First-party announcement" : "Analysis"}</span>}<span> / </span><time dateTime={s.publishedAt}>{new Intl.DateTimeFormat("en-US", { timeZone: edition.timezone, month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(s.publishedAt))}</time>{s.collectors.some(name => discoveryNames[name]) && <span> / Via {s.collectors.map(name => discoveryNames[name]).filter(Boolean).join(", ")}</span>}{reader.read.includes(s.id) && <span> / Read</span>}</p>; }
  function brief(s: EditionStory) { return <article className="brief" key={s.id}><Picture story={s} small /><a className="headline-link" href={reportHref(s)}><h4 className={s.title.length > 120 ? "long-headline" : undefined}>{s.title}</h4></a>{s.summary && <p className="brief-summary">{s.summary}</p>}{meta(s)}<div className="brief-tail"><a href={s.url} target="_blank" rel="noreferrer">Original <ArrowUpRight /></a>{actions(s)}</div></article>; }
  function major(s: EditionStory, i: number, items: EditionStory[]) { return <article className="major-report" id={`report-${s.id}`} key={s.id}>
    <div className="report-top"><span>{String(i + 1).padStart(2, "0")} / MAJOR REPORT</span><span className="priority" title="Editorial priority, not a credibility rating">{s.score.toFixed(1)} / 10</span><button className="tool" disabled={i === 0 || !ready} title="Move up within sector" aria-label="Move up within sector" onClick={() => move(s.id, -1, items)}><ArrowUp /></button><button className="tool" disabled={i === items.length - 1 || !ready} title="Move down within sector" aria-label="Move down within sector" onClick={() => move(s.id, 1, items)}><ArrowDown /></button></div>
    <a className="headline-link" href={reportHref(s)}><h3 className={s.title.length > 120 ? "long-headline" : undefined}>{s.title}</h3></a>{meta(s)}<div className="report-copy"><Picture story={s} />{s.summary && <p className="excerpt">{s.summary}</p>}</div>
    <div className="report-tail"><a href={s.url} target="_blank" rel="noreferrer">Read at {s.publisher} <ArrowUpRight /></a>{actions(s)}</div>
    <a className="coverage-link" href={reportHref(s)}>{s.coverage.length > 1 ? `${s.coverage.length} linked reports` : "Story details"} <ArrowUpRight /></a>
  </article>; }
  function changeView(next: EditionView) { if (initialStory) { window.location.assign(`${home}?view=${encodeURIComponent(next)}`); return; } setView(next); setQuery(""); setTopic("All sectors"); }
  return <main className="news-edition">
    <a className="skip-link" href="#edition-content">Skip to news</a>
    {staticMode && <nav className="edition-history-nav" aria-label="Edition history"><a href="/">Latest edition</a><a href="/editions/">Past editions</a><a href={`/editions/${edition.date}/`}>Permanent edition link</a></nav>}
    <header className="newspaper-head"><div className="masthead-main"><h1><a href={home}>News 4 u.</a></h1><div className="edition-date"><time dateTime={edition.date}>{new Intl.DateTimeFormat("en-US", { timeZone: "UTC", weekday: "long", month: "long", day: "numeric", year: "numeric" }).format(new Date(`${edition.date}T12:00:00Z`))}</time><span>THE DAILY EDITION / {edition.timezone}</span></div></div>
    <div className="edition-nav-row"><nav aria-label="Collections">{(["Today", "I do not have time", "Catch up", "Saved", "Archived"] as EditionView[]).map(v => <button key={v} aria-current={!initialStory && view === v ? "page" : undefined} onClick={() => changeView(v)}>{v === "Today" && archivedEdition ? "Edition" : v}{v === "Saved" ? ` ${reader.saved.length}` : ""}</button>)}</nav><div className="utility-nav"><ThemePicker /><button onClick={() => changeView("Sources")} aria-current={view === "Sources" ? "page" : undefined}>Sources</button><button className="tool" title="Reader preferences" aria-label="Reader preferences" onClick={() => changeView("Settings")}><Settings /></button><button className="tool" title="Mark visible stories read" aria-label="Mark visible stories read" disabled={!ready || !visible.length} onClick={() => { update({ ...reader, read: [...new Set([...reader.read, ...visible.map(s => s.id)])] }); setNotice("Visible stories marked read"); }}><CheckCheck /></button></div></div></header>
    {!initialStory && view !== "I do not have time" && view !== "Sources" && view !== "Settings" && <><div className="edition-filters"><nav aria-label="Sectors">{["All sectors", ...topics].map(t => <button key={t} aria-pressed={t === topic} onClick={() => setTopic(t)}>{t}</button>)}</nav><div className="filter-tools"><label className="ranking">STORY ORDER <select aria-label="Rank stories within each sector" value={sort} onChange={e => setSort(e.target.value)}><option value="editorial">Editorial priority</option><option value="latest">Latest first</option><option value="custom">Your order</option></select></label><label className="edition-search"><Search /><input aria-label="Search the edition" placeholder="Search the edition" type="search" value={query} onChange={e => setQuery(e.target.value)} /></label></div></div><nav className="sector-index" aria-label="Jump to sector"><span>{view === "Today" ? "The day's sectors" : view}</span><div>{groups.map((g, i) => <a key={g.name} href={`#sector-${g.name.toLowerCase()}`}>{String(i + 1).padStart(2, "0")} {g.name}</a>)}</div><small>{visible.length} STORIES</small></nav></>}
    <div id="edition-content">
    {initialStory ? (story ? <article className="report-page reader-body"><a className="back-to-edition" href={home}>Back to the edition</a><p className="sector-label">{story.sector}</p><h2 id="reader-title">{story.title}</h2>{meta(story)}<Picture story={story} />{story.summary && <p>{story.summary}</p>}<ReportNotes story={story} /><div className="report-tail"><a href={story.url} target="_blank" rel="noreferrer">Read original <ArrowUpRight /></a>{actions(story)}</div>{story.coverage.length > 1 && <><h3>Across the reporting</h3>{story.coverage.map(item => <a className="coverage-row" key={item.url} href={item.url} target="_blank" rel="noreferrer"><span>{item.title}<small>{item.publisher}</small></span><ArrowUpRight /></a>)}</>}</article> : <section className="empty-edition"><h2>Report unavailable</h2><a href={home}>Back to the edition</a></section>) : view === "I do not have time" ? <section className="daily-briefing"><header><p className="sector-label">THE SHORT EDITION</p><h2>I do not have time</h2><p className="section-meta">{topStories.length} top stories / {edition.date}</p></header>{topStories.map((s, i) => <article className="briefing-story" key={s.id}><span className="briefing-number">{String(i + 1).padStart(2, "0")}</span><div><p className="sector-label">{s.sector} / {s.publisher}</p><a href={reportHref(s)} className="headline-link"><h3>{s.title}</h3></a>{s.summary && <p className="briefing-summary">{s.summary.length > 180 ? `${s.summary.slice(0, 177).replace(/\s+\S*$/, "")}...` : s.summary}</p>}</div></article>)}{!topStories.length && <p>No current stories match your preferences.</p>}</section> : view === "Sources" ? <section className="reader-section"><h2>Sources</h2><p className="section-meta">Collected {new Date(edition.generatedAt).toLocaleString("en-US", { timeZone: edition.timezone })}</p><div className="source-table">{edition.sources.map(source => <div className="source-row" key={source.name}><strong>{source.name}</strong><span>{source.status}</span><span>{source.published ?? 0} published</span><small>{source.collected ?? 0} collected / {source.eligible ?? 0} eligible / {source.reviewed ?? 0} reviewed. {source.reason || (source.latest ? `Latest: ${source.latest.slice(0, 10)}` : "No dated items")}</small></div>)}</div></section> : view === "Settings" ? <section className="reader-section"><h2>Reader preferences</h2><h3>Publishers</h3>{[...new Set(edition.stories.map(s => s.publisher))].sort().map(name => <label className="publisher-setting" key={name}><input type="checkbox" checked={!reader.hiddenSources.includes(name)} onChange={() => update({ ...reader, hiddenSources: reader.hiddenSources.includes(name) ? reader.hiddenSources.filter(s => s !== name) : [...reader.hiddenSources, name] })} />{name}</label>)}</section> : groups.length ? groups.map(group => {
      // Each lead and its briefs are one normal-flow spread; nothing pins or scrolls independently.
      if (group.name === "Sports") return <SportsSection key="sports" data={view === "Today" ? edition.sports : undefined} stories={group.stories} timezone={edition.timezone} renderLead={(story, items) => major(story, 0, items)} renderBrief={brief} />;
      const count = Math.max(1, Math.ceil(group.stories.length / 3));
      const leads = group.stories.slice(0, count), briefs = group.stories.slice(count);
      return <section className="news-sector" key={group.name} id={`sector-${group.name.toLowerCase()}`}><h2 className="sector-label">{group.name}</h2>{leads.map((s, i) => { const side = briefs.slice(i * 2, i * 2 + 2); return <div className={`shared-spread ${i % 2 ? "reverse" : ""} ${side.length ? "" : "solo"}`} key={s.id}>{major(s, i, group.stories)}{side.length > 0 && <aside className="spread-briefs"><h3>Also in {group.name.toLowerCase()}</h3>{side.map(brief)}</aside>}</div>; })}</section>;
    }) : <section className="empty-edition"><h2>{edition.stories.length ? "No stories here." : "No edition has been collected yet."}</h2>{edition.stories.length > 0 && <button onClick={() => { changeView("Today"); setQuery(""); }}>Back to today</button>}</section>}
    </div>
    <footer className="newspaper-footer"><span>News 4 u.</span><time dateTime={edition.generatedAt}>Updated {new Intl.DateTimeFormat("en-US", { timeZone: edition.timezone, month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(edition.generatedAt))}</time><span>{edition.stories.length} stories / {dateInZone(edition.generatedAt, edition.timezone)}</span></footer>
    <div className="edition-toast" role="status" hidden={!notice}>{notice}</div>
  </main>;
}
