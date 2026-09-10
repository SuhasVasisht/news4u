import { ArrowUpRight } from "lucide-react";
import type { ReactNode } from "react";
import { sportsGamesForDisplay, type EditionStory, type SportsData } from "@/lib/edition";

type Props = { data?: SportsData; stories: EditionStory[]; timezone: string; renderLead: (story: EditionStory, items: EditionStory[]) => ReactNode; renderBrief: (story: EditionStory) => ReactNode };

export function SportsSection({ data, stories, timezone, renderLead, renderBrief }: Props) {
  const date = (value: string) => new Intl.DateTimeFormat("en-US", { timeZone: timezone, month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" }).format(new Date(value));
  return <section className="news-sector sports-section" id="sector-sports" aria-labelledby="sports-title">
    <header className="sports-header"><div><p className="sector-label">THE BACK PAGE</p><h2 id="sports-title">Sports in brief</h2></div>{data && <p className="section-meta">Snapshot <time dateTime={data.checkedAt}>{date(data.checkedAt)}</time><br />ESPN scores & standings</p>}</header>
    {["NFL", "Soccer", "NBA"].map(group => {
      const leagues = data?.leagues.filter(l => l.group === group) || [];
      const items = stories.filter(s => s.sportsGroup === group);
      if (!items.length && !leagues.length) return null;
      return <section className="sports-roundup" key={group} aria-label={`${group} roundup`}><h3 className="sector-label">{group}</h3>
        <div className={`shared-spread sports-spread ${leagues.length ? "" : "solo"}`}>
        <div className="sports-stories">
          {items[0] ? renderLead(items[0], items) : <p className="sports-muted">No new headline selected.</p>}
          {items.length > 1 && <div className="sports-supporting">{items.slice(1).map(renderBrief)}</div>}
        </div>
        {leagues.length > 0 && <aside className="spread-briefs sports-scoreboard" aria-label={`${group} scores`}><h3>Scores & fixtures</h3>
        {leagues.map((league, index) => <details className="sports-league" key={league.id} open={index === 0}>
          <summary>{league.name}<span>{league.scheduleStatus === "unavailable" ? "Scores unavailable" : league.games.length ? `${league.games.length} games / ${league.games.filter(g => g.completed).length} final` : "No games in this window"}</span></summary>
          <p className="section-meta">{league.season} / Past 24 hours & next 24 hours</p>
          {league.scheduleStatus === "unavailable" ? <p className="sports-muted">Score feed unavailable at collection.</p> : !league.games.length ? <p className="sports-muted">No games scheduled in this window.</p> : <ul className="sports-games">{sportsGamesForDisplay(league.games).map(game => <li key={game.id}>
            <a href={game.url} target="_blank" rel="noreferrer"><span>{game.away.name}<small>AWAY</small></span><strong>{game.away.score ?? "-"}</strong><span>{game.home.name}<small>HOME</small></span><strong>{game.home.score ?? "-"}</strong></a>
            <p><span className={game.state === "in" ? "sports-in-progress" : ""}>{game.state === "in" ? "In progress at collection: " : ""}{game.detail}</span><time dateTime={game.date}>{date(game.date)}</time></p>
          </li>)}</ul>}
          {league.games.length > 6 && <p className="sports-muted">Showing 6 of {league.games.length} games.</p>}
          <details className="sports-standings"><summary>Standings</summary>{league.standingsStatus === "unavailable" ? <p className="sports-muted">Standings unavailable at collection.</p> : league.tables.map((table, i) => <div className="sports-table" key={i}>
            <p className="section-meta">{table.season} / {table.name}</p>
            {table.url && <a className="sports-full-link" href={table.url} target="_blank" rel="noreferrer">Full standings <ArrowUpRight /></a>}
            {!table.started ? <p className="sports-muted">No completed games recorded in this table yet.</p> : <table><caption>Standings: top three</caption><thead><tr><th scope="col">Team</th><th scope="col">{group === "Soccer" ? "W-L-D" : group === "NFL" ? "W-L-T" : "W-L"}</th>{group === "Soccer" && <th scope="col">Pts</th>}</tr></thead><tbody>{table.rows.map(row => <tr key={row.team}><th scope="row">{row.rank !== null && <span>{row.rank} </span>}{row.team}</th><td>{row.record}</td>{group === "Soccer" && <td>{row.points}</td>}</tr>)}</tbody></table>}
          </div>)}</details>
          <a className="sports-full-link" href={league.url} target="_blank" rel="noreferrer">Full scoreboard <ArrowUpRight /></a>
        </details>)}</aside>}
        </div>
      </section>;
    })}
    {stories.some(s => s.sportsGroup === "Elsewhere") && <section className="sports-elsewhere"><h3>Elsewhere in sport</h3><div>{stories.filter(s => s.sportsGroup === "Elsewhere").map(renderBrief)}</div></section>}
  </section>;
}
