import type { AppPreferences, Source, SyncArticleInput, Topic } from "@/lib/types";

export const mockSources: Source[] = [
  {
    id: "src-atlas",
    slug: "atlas-wire",
    name: "Atlas Wire",
    homepageUrl: "https://atlas-wire.example.com",
    iconUrl: null,
  },
  {
    id: "src-market",
    slug: "market-beat",
    name: "Market Beat",
    homepageUrl: "https://market-beat.example.com",
    iconUrl: null,
  },
  {
    id: "src-grid",
    slug: "grid-log",
    name: "Grid Log",
    homepageUrl: "https://grid-log.example.com",
    iconUrl: null,
  },
];

export const mockTopics: Topic[] = [
  { id: "top-tech", slug: "technology", name: "Technology" },
  { id: "top-policy", slug: "policy", name: "Policy" },
  { id: "top-energy", slug: "energy", name: "Energy" },
  { id: "top-markets", slug: "markets", name: "Markets" },
];

function hoursAgo(hours: number) {
  return new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
}

export const sampleSyncPayload: SyncArticleInput[] = [
  {
    external_id: "atlas-001",
    title: "Open-model startups shift from demos to durable enterprise contracts",
    summary:
      "AI infra vendors are closing budget-backed deals around routing, observability, and governance instead of generic pilots.",
    author: "Mina Cross",
    url: "https://atlas-wire.example.com/open-model-contracts",
    image_url: null,
    published_at: hoursAgo(2),
    content_text:
      "Enterprise AI buyers are moving toward measurable tooling, focusing on compliance, routing, and cost controls. Procurement teams are rewarding narrower products that shorten implementation time and reduce vendor lock-in.",
    score: 9.4,
    source: {
      slug: "atlas-wire",
      name: "Atlas Wire",
      homepage_url: "https://atlas-wire.example.com",
      icon_url: null,
    },
    topics: [
      { slug: "technology", name: "Technology" },
      { slug: "markets", name: "Markets" },
    ],
  },
  {
    external_id: "market-204",
    title: "Open-model startups move from demos into multi-year enterprise contracts",
    summary:
      "Investors see more durable revenue in tooling that sits between model providers and finance buyers.",
    author: "Eli Ramirez",
    url: "https://market-beat.example.com/open-model-revenue",
    image_url: null,
    published_at: hoursAgo(5),
    content_text:
      "Public market analysts are treating AI infrastructure as a cost-control story rather than a consumer novelty wave. The strongest demand is flowing to products that make model usage auditable and contractable.",
    score: 8.9,
    source: {
      slug: "market-beat",
      name: "Market Beat",
      homepage_url: "https://market-beat.example.com",
      icon_url: null,
    },
    topics: [
      { slug: "technology", name: "Technology" },
      { slug: "markets", name: "Markets" },
    ],
  },
  {
    external_id: "market-205",
    title: "Treasury markets absorb another noisy inflation print without a broad selloff",
    summary:
      "Rates traders are treating the latest report as a policy complication, not a full regime change.",
    author: "Eli Ramirez",
    url: "https://market-beat.example.com/treasury-inflation",
    image_url: null,
    published_at: hoursAgo(8),
    content_text:
      "Bond desks entered the session expecting volatility, but price action remained contained. Analysts pointed to stronger hedging demand and a belief that the central bank can wait for broader labor market softness before making its next move.",
    score: 8.7,
    source: {
      slug: "market-beat",
      name: "Market Beat",
      homepage_url: "https://market-beat.example.com",
      icon_url: null,
    },
    topics: [
      { slug: "markets", name: "Markets" },
      { slug: "policy", name: "Policy" },
    ],
  },
  {
    external_id: "grid-588",
    title: "Grid operators pay more attention to battery dispatch during evening peaks",
    summary:
      "Regional planners say storage assets are now changing the shape of reserve planning, not just adding extra megawatts.",
    author: "Talia Grant",
    url: "https://grid-log.example.com/battery-dispatch",
    image_url: null,
    published_at: hoursAgo(20),
    content_text:
      "Storage projects are being evaluated on operational responsiveness rather than raw size. Utilities are modeling dispatch windows, local congestion, and weather-linked demand with more granularity than a year ago.",
    score: 8.9,
    source: {
      slug: "grid-log",
      name: "Grid Log",
      homepage_url: "https://grid-log.example.com",
      icon_url: null,
    },
    topics: [{ slug: "energy", name: "Energy" }],
  },
  {
    external_id: "atlas-002",
    title: "State privacy bills converge on narrower compliance carve-outs for internal AI tools",
    summary:
      "Legal teams are seeing lawmakers focus less on outright bans and more on oversight and documentation.",
    author: "Mina Cross",
    url: "https://atlas-wire.example.com/privacy-bills-ai-tools",
    image_url: null,
    published_at: hoursAgo(28),
    content_text:
      "Draft bills increasingly distinguish consumer-facing automated decisions from internal productivity systems. That distinction is giving enterprises clearer compliance paths but raising documentation requirements around model monitoring and vendor access.",
    score: 7.8,
    source: {
      slug: "atlas-wire",
      name: "Atlas Wire",
      homepage_url: "https://atlas-wire.example.com",
      icon_url: null,
    },
    topics: [
      { slug: "policy", name: "Policy" },
      { slug: "technology", name: "Technology" },
    ],
  },
  {
    external_id: "grid-589",
    title: "Battery dispatch planning becomes central to evening grid reliability",
    summary:
      "Operators are treating batteries as active balancing tools instead of backup capacity.",
    author: "Talia Grant",
    url: "https://grid-log.example.com/evening-grid-reliability",
    image_url: null,
    published_at: hoursAgo(34),
    content_text:
      "System operators say batteries are increasingly used to smooth evening ramps and defer peaker use. That is changing the assumptions behind reserve scheduling and congestion models.",
    score: 8.4,
    source: {
      slug: "grid-log",
      name: "Grid Log",
      homepage_url: "https://grid-log.example.com",
      icon_url: null,
    },
    topics: [{ slug: "energy", name: "Energy" }],
  },
];

export const mockAppPreferences: AppPreferences = {
  theme: "system",
  feedDensity: "comfortable",
  openOriginalInNewTab: true,
};
