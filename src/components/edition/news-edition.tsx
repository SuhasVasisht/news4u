"use client";

import { useEffect, useState } from "react";
import { ArrowUpRight, ChevronDown, Search, X } from "lucide-react";
import { briefingStories, sectorStories, type EditionData, type EditionStory, type EditionView } from "@/lib/edition";
import { SportsSection } from "./sports-section";
import { ThemePicker } from "./theme-picker";
import { NewsMark } from "./news-mark";

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
  const normalizeView = (value: string | null): "Today" | "I do not have time" | "Sources" => value === "I do not have time" || value === "Sources" ? value : "Today";
  const [view, setView] = useState(normalizeView(initialView));
  const [query, setQuery] = useState(initialQuery);
  const [searchOpen, setSearchOpen] = useState(Boolean(initialQuery));
  const home = staticMode ? "./index.html" : "/";
  const reportHref = (s: EditionStory) => staticMode ? `./report-${encodeURIComponent(s.id)}.html` : `/story/${encodeURIComponent(s.id)}`;
  useEffect(() => {
    setView(normalizeView(new URLSearchParams(location.search).get("view") || initialView));
    if (new URLSearchParams(location.search).get("search") === "1") setSearchOpen(true);
  }, [initialView]);
  // An edition is a published document, not a personal inbox. Legacy reader state is deliberately ignored.
  const visible = edition.stories.filter(s => (initialSector === "All sectors" || s.sector === initialSector) && `${s.title} ${s.summary} ${s.publisher}`.toLowerCase().includes(query.toLowerCase()));
  const topics = [...new Set([...sectors, ...edition.stories.map(s => s.sector)])].filter(s => edition.stories.some(story => story.sector === s) || (s === "Sports" && edition.sports));
  const groups = topics.map(name => ({ name, stories: sectorStories(visible.filter(s => s.sector === name), "editorial", []) })).filter(g => g.stories.length || (g.name === "Sports" && edition.sports && !query && initialSector === "All sectors"));
  const story = edition.stories.find(s => s.id === initialStory);
  const topStories = briefingStories(visible);
  function meta(s: EditionStory) { return <p className="byline">{s.publisher}{s.kind && s.kind !== "reporting" && <span> / {s.kind === "podcast" ? "Podcast" : s.kind === "announcement" ? "First-party announcement" : "Analysis"}</span>}<span> / </span><time dateTime={s.publishedAt}>{new Intl.DateTimeFormat("en-US", { timeZone: edition.timezone, month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(s.publishedAt))}</time>{s.collectors.some(name => discoveryNames[name]) && <span> / Via {s.collectors.map(name => discoveryNames[name]).filter(Boolean).join(", ")}</span>}</p>; }
  function brief(s: EditionStory) { return <article className="brief" key={s.id}><Picture story={s} small /><a className="headline-link" href={reportHref(s)}><h4 className={s.title.length > 120 ? "long-headline" : undefined}>{s.title}</h4></a>{s.summary && <p className="brief-summary">{s.summary}</p>}{meta(s)}<div className="brief-tail"><a href={s.url} target="_blank" rel="noreferrer">Original <ArrowUpRight /></a></div></article>; }
  function major(s: EditionStory) { return <article className="major-report" id={`report-${s.id}`} key={s.id}>
    <a className="headline-link" href={reportHref(s)}><h3 className={s.title.length > 120 ? "long-headline" : undefined}>{s.title}</h3></a>{meta(s)}<div className="report-copy"><Picture story={s} />{s.summary && <p className="excerpt">{s.summary}</p>}</div>
    <div className="report-tail"><a href={s.url} target="_blank" rel="noreferrer">Read at {s.publisher} <ArrowUpRight /></a>{s.coverage.length > 1 && <a className="coverage-link" href={reportHref(s)}>{s.coverage.length} linked reports <ArrowUpRight /></a>}</div>
  </article>; }
  function changeView(next: "Today" | "I do not have time" | "Sources") {
    if (initialStory) { window.location.assign(`${home}?view=${encodeURIComponent(next)}`); return; }
    setView(next); setQuery(""); setSearchOpen(false);
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  return <main className="news-edition newspaper-reader">
    <a className="skip-link" href="#edition-content">Skip to news</a>
    <header className="newspaper-head"><div className="masthead-main"><h1><a href={home}><NewsMark />News 4 u.</a></h1><div className="edition-date"><time dateTime={edition.date}>{new Intl.DateTimeFormat("en-US", { timeZone: "UTC", weekday: "long", month: "long", day: "numeric", year: "numeric" }).format(new Date(`${edition.date}T12:00:00Z`))}</time></div></div>
    <div className="edition-nav-row">
      <nav aria-label="Edition views"><button aria-current={!initialStory && view === "Today" ? "page" : undefined} onClick={() => changeView("Today")}>{archivedEdition ? "Edition" : "The paper"}</button><button aria-current={!initialStory && view === "I do not have time" ? "page" : undefined} onClick={() => changeView("I do not have time")}>I do not have time</button></nav>
      <div className="utility-nav">
        <details className="section-menu" onKeyDown={event => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.open = false; }}>
          <summary aria-label="Sections" title="Sections"><span>Sections</span> <ChevronDown /></summary><nav aria-label="Newspaper sections">{topics.map(name => <a key={name} href={`${initialStory || view !== "Today" ? home : ""}#sector-${name.toLowerCase()}`} onClick={event => { event.currentTarget.closest("details")?.removeAttribute("open"); }}>{name}</a>)}</nav>
        </details>
        <button className="tool" title="Search the paper" aria-label="Search the paper" aria-expanded={searchOpen} aria-controls="paper-search" onClick={() => {
          if (initialStory) { window.location.assign(`${home}?search=1`); return; }
          setSearchOpen(value => !value); setQuery("");
        }}><Search /></button><ThemePicker />
      </div>
    </div></header>
    {searchOpen && !initialStory && <div className="paper-search" id="paper-search"><label className="edition-search"><Search /><input autoFocus aria-label="Search the edition" placeholder="Search the edition" type="search" value={query} onChange={e => setQuery(e.target.value)} /></label><button className="tool" title="Close search" aria-label="Close search" onClick={() => { setQuery(""); setSearchOpen(false); }}><X /></button></div>}
    <div id="edition-content">
    {initialStory ? (story ? <article className="report-page reader-body"><a className="back-to-edition" href={home}>Back to the edition</a><p className="sector-label">{story.sector}</p><h2 id="reader-title">{story.title}</h2>{meta(story)}<Picture story={story} />{story.summary && <p>{story.summary}</p>}<ReportNotes story={story} /><div className="report-tail"><a href={story.url} target="_blank" rel="noreferrer">Read original <ArrowUpRight /></a></div>{story.coverage.length > 1 && <><h3>Across the reporting</h3>{story.coverage.map(item => <a className="coverage-row" key={item.url} href={item.url} target="_blank" rel="noreferrer"><span>{item.title}<small>{item.publisher}</small></span><ArrowUpRight /></a>)}</>}</article> : <section className="empty-edition"><h2>Report unavailable</h2><a href={home}>Back to the edition</a></section>) : view === "I do not have time" ? <section className="daily-briefing"><header><p className="sector-label">THE SHORT EDITION</p><h2>I do not have time</h2></header>{topStories.map((s, i) => <article className="briefing-story" key={s.id}><span className="briefing-number">{String(i + 1).padStart(2, "0")}</span><div><p className="sector-label">{s.sector} / {s.publisher}</p><a href={reportHref(s)} className="headline-link"><h3>{s.title}</h3></a>{s.summary && <p className="briefing-summary">{s.summary.length > 180 ? `${s.summary.slice(0, 177).replace(/\s+\S*$/, "")}...` : s.summary}</p>}</div></article>)}{!topStories.length && <p>No stories match your search.</p>}</section> : view === "Sources" ? <section className="reader-section"><h2>Sources</h2><p className="section-meta">Collected {new Date(edition.generatedAt).toLocaleString("en-US", { timeZone: edition.timezone })}</p><div className="source-table">{edition.sources.map(source => <div className="source-row" key={source.name}><strong>{source.name}</strong><span>{source.status}</span><span>{source.published ?? 0} published</span><small>{source.collected ?? 0} collected / {source.eligible ?? 0} eligible / {source.reviewed ?? 0} reviewed. {source.reason || (source.latest ? `Latest: ${source.latest.slice(0, 10)}` : "No dated items")}</small></div>)}</div></section> : groups.length ? groups.map(group => {
      if (group.name === "Sports") return <SportsSection key="sports" data={edition.sports} stories={group.stories} timezone={edition.timezone} renderLead={major} renderBrief={brief} />;
      const count = Math.max(1, Math.ceil(group.stories.length / 3));
      const leads = group.stories.slice(0, count), briefs = group.stories.slice(count);
      return <section className="news-sector" key={group.name} id={`sector-${group.name.toLowerCase()}`}><h2 className="sector-label">{group.name}</h2>{leads.map((s, i) => { const side = briefs.slice(i * 2, i * 2 + 2); return <div className={`shared-spread ${i % 2 ? "reverse" : ""} ${side.length ? "" : "solo"}`} key={s.id}>{major(s)}{side.length > 0 && <aside className="spread-briefs"><h3>Also in {group.name.toLowerCase()}</h3>{side.map(brief)}</aside>}</div>; })}</section>;
    }) : <section className="empty-edition"><h2>{edition.stories.length ? "No matching stories." : "No edition has been collected yet."}</h2>{edition.stories.length > 0 && <button onClick={() => changeView("Today")}>Back to the paper</button>}</section>}
    </div>
    <footer className="newspaper-footer"><span>News 4 u.</span><nav aria-label="Edition information">{staticMode && <><a href="/">Latest edition</a><a href="/editions/">Past editions</a><a href={`/editions/${edition.date}/`}>Permanent edition link</a></>}<button onClick={() => changeView("Sources")}>Sources</button></nav><time dateTime={edition.generatedAt}>Updated {new Intl.DateTimeFormat("en-US", { timeZone: edition.timezone, month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(edition.generatedAt))}</time></footer>
  </main>;
}
