import {
  Activity,
  AlertTriangle,
  Beaker,
  BookOpen,
  Check,
  ChevronRight,
  Clipboard,
  Clock3,
  Database,
  Download,
  FileJson,
  Filter,
  Gauge,
  Home,
  Info,
  Layers3,
  Menu,
  Network,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { downloadCsv, downloadJson, loadCertificate, loadExperiments, loadStatus, loadThemes } from "./data";
import { EvidenceDrawer } from "./components/EvidenceDrawer";
import { EvidenceGraph } from "./components/EvidenceGraph";
import { StatusBadge } from "./components/StatusBadge";
import { ThemeCard } from "./components/ThemeCard";
import type { Certificate, Experiment, Status, Theme } from "./types";

const nav = [
  ["today", "Today", Home],
  ["themes", "Themes", Layers3],
  ["evidence", "Evidence", Network],
  ["certificates", "Certificates", FileJson],
  ["experiments", "Experiments", Beaker],
  ["data-quality", "Data Quality", Database],
  ["methodology", "Methodology", BookOpen],
  ["research", "Research", Search],
  ["status", "Status", Activity],
] as const;

type Route = (typeof nav)[number][0];
const validRoutes = new Set(nav.map(([route]) => route));

function routeFromHash(): Route {
  const route = window.location.hash.replace(/^#\/?/, "").split(/[/?]/)[0] || "today";
  return validRoutes.has(route as Route) ? route as Route : "today";
}

function routeTo(route: Route, theme?: string) {
  window.location.hash = theme ? `/${route}?theme=${theme}` : `/${route}`;
}

function themeFromHash(): string | null {
  return new URLSearchParams(window.location.hash.split("?")[1] ?? "").get("theme");
}

function formatTime(date: Date, zone: "ET" | "UTC", options: Intl.DateTimeFormatOptions = {}) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: zone === "ET" ? "America/New_York" : "UTC",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    ...options,
  }).format(date);
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <div className="empty-state"><Info /><h3>{title}</h3><p>{detail}</p></div>;
}

function SectionHeader({ eyebrow, title, detail }: { eyebrow: string; title: string; detail: string }) {
  return <header className="section-header"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{detail}</p></header>;
}

function ReadinessLegend() {
  return <div className="readiness-legend" role="region" aria-label="Readiness legend" tabIndex={0}>
    <span><abbr title="Required point-in-time inputs are complete"><strong>DATA_READY</strong></abbr> inputs complete</span>
    <ChevronRight aria-hidden="true" />
    <span><abbr title="A frozen model has calculated a signed or unsigned state"><strong>MODEL_ESTIMATED</strong></abbr> state calculated</span>
    <ChevronRight aria-hidden="true" />
    <span><abbr title="All preregistered evidence and risk gates have passed"><strong>DECISION_ELIGIBLE</strong></abbr> evidence gate passed</span>
  </div>;
}

function TodayPage({ status, themes, certificates, onOpenTheme, onEvidence, zone }: {
  status: Status; themes: Theme[]; certificates: Record<string, Certificate>; onOpenTheme: (id: string) => void; onEvidence: (item: Certificate) => void; zone: "ET" | "UTC";
}) {
  const now = new Date();
  const timeline = [
    ["09:20", "Runtime start", "pending"],
    ["09:30", "Open snapshot", "pending"],
    ["12:00", "Midday snapshot", "pending"],
    ["15:30", "Preclose snapshot", "captured"],
    ["15:45", "Decision snapshot", "captured"],
    ["16:00", "Close diagnostic", "captured"],
  ];
  return <>
    <section className="today-hero">
      <div className="today-copy">
        <p className="eyebrow">System operating view</p>
        <h1>Today</h1>
        <div className="live-clock"><Clock3 /><span>{formatTime(now, zone)}</span><small>{zone}</small></div>
        <p className="hero-summary">Point-in-time evidence collection is the active layer. Models, decisions, paper positions, and live orders remain disabled.</p>
        <div className="hero-badges"><StatusBadge label="SYSTEM HEALTHY" state="ready" /><StatusBadge label="DATA SHADOW 0 / 20" state="warning" /><StatusBadge label="NO DECISION" state="neutral" /></div>
      </div>
      <div className="graph-panel"><div className="graph-label">Evidence system</div><EvidenceGraph /><div className="graph-foot">Structured lineage, not a trade signal</div></div>
    </section>
    <ReadinessLegend />
    <section className="metric-strip" aria-label="Current system metrics">
      <div><span>Updated</span><strong>{formatTime(new Date(status.updated_at), zone, { month: "short", day: "numeric" })}</strong></div>
      <div><span>Core themes</span><strong>6 / 6</strong></div>
      <div><span>Missing points</span><strong>2</strong></div>
      <div><span>Positions / orders</span><strong>{status.paper_positions} / {status.real_orders}</strong></div>
    </section>
    <section className="content-band">
      <div className="band-header"><div><p className="eyebrow">Observation chain</p><h2>Today&apos;s timeline</h2></div><p>Latest published evidence is the Aug 10 partial rehearsal.</p></div>
      <ol className="session-timeline">{timeline.map(([time, label, state]) => <li key={time} className={state}><time>{time}</time><span>{label}</span><small>{state === "captured" ? "Captured in rehearsal" : "Missed, not backfilled"}</small></li>)}</ol>
    </section>
    <section className="content-band">
      <div className="band-header"><div><p className="eyebrow">Six frozen themes</p><h2>Evidence states</h2></div><p>Readiness and signed state remain separate.</p></div>
      <div className="theme-grid">{themes.map((theme) => <ThemeCard key={theme.theme_id} theme={theme} certificate={certificates[theme.theme_id]} onOpen={() => onOpenTheme(theme.theme_id)} onEvidence={() => certificates[theme.theme_id] && onEvidence(certificates[theme.theme_id])} />)}</div>
    </section>
    <section className="boundary-band"><ShieldCheck /><div><h2>Evidence boundary</h2><p>{status.next_milestone}</p></div><strong>NO BUY / SELL OUTPUT</strong></section>
  </>;
}

function ThemeDetail({ theme, certificate, onEvidence }: { theme: Theme; certificate: Certificate; onEvidence: () => void }) {
  const detailMetrics = [
    ["15:30 quote", "Data ready", "Readiness only"],
    ["15:45 quote", "Data ready", "Readiness only"],
    ["ETF vs benchmark", "Not estimated", "Model disabled"],
    ["VWAP position", "Input captured", "No signed interpretation"],
    ["Breadth", "Not estimated", "Transmission disabled"],
    ["Median residual", "Not estimated", "Transmission disabled"],
    ["Volume breadth", "Not estimated", "Transmission disabled"],
    ["Concentration", "Not estimated", "Fragility disabled"],
  ];
  return <>
    <SectionHeader eyebrow={`${theme.tracker_etf} · Theme detail`} title={theme.display_name} detail="Point-in-time state components, conflicts, invalidation, and source lineage." />
    <ReadinessLegend />
    <div className="detail-layout">
      <section className="detail-main">
        <div className="panel-header"><h2>Observation state</h2><StatusBadge label="DATA READY ONLY" state="warning" /></div>
        <div className="metric-table">{detailMetrics.map(([name, value, note]) => <div key={name}><span>{name}</span><strong>{value}</strong><small>{note}</small></div>)}</div>
        <section className="unframed-section"><h2>Observer evidence</h2><div className="observer-row"><span>Direction</span><b>unresolved</b><span>Transmission</span><b>not estimable</b><span>Episode</span><b>not estimable</b></div></section>
        <section className="unframed-section"><h2>Episode timeline</h2><EmptyState title="Sequential evidence not available" detail="Episode inference begins only after a legal prospective sequence exists." /></section>
      </section>
      <aside className="certificate-summary">
        <p className="eyebrow">State Certificate</p><h2>{certificate.decision_status.replaceAll("_", " ")}</h2>
        <h3>Why</h3>{certificate.facts.map((fact) => <p key={fact.text}>{fact.text}</p>)}
        <h3>Invalidation</h3><p>{certificate.invalidation[0]}</p>
        <h3>Next probe</h3><p>{certificate.next_probe.acquire}</p>
        <button className="command-button" onClick={onEvidence}>Open evidence <Network /></button>
      </aside>
    </div>
  </>;
}

function ThemesPage({ themes, certificates, selectedTheme, onSelect, onEvidence }: { themes: Theme[]; certificates: Record<string, Certificate>; selectedTheme: string | null; onSelect: (id: string) => void; onEvidence: (item: Certificate) => void }) {
  if (selectedTheme) {
    const theme = themes.find((item) => item.theme_id === selectedTheme);
    const certificate = certificates[selectedTheme];
    if (theme && certificate) return <ThemeDetail theme={theme} certificate={certificate} onEvidence={() => onEvidence(certificate)} />;
  }
  return <><SectionHeader eyebrow="Frozen universe" title="Themes" detail="Six stable research units with distinct data readiness, model state, and decision eligibility." /><div className="theme-grid">{themes.map((theme) => <ThemeCard key={theme.theme_id} theme={theme} certificate={certificates[theme.theme_id]} onOpen={() => onSelect(theme.theme_id)} onEvidence={() => onEvidence(certificates[theme.theme_id])} />)}</div></>;
}

function EvidencePage({ themes, certificates, onEvidence }: { themes: Theme[]; certificates: Record<string, Certificate>; onEvidence: (item: Certificate) => void }) {
  return <><SectionHeader eyebrow="Auditable lineage" title="Evidence" detail="Every model-like statement must retain observer, timestamp, uncertainty, threshold source, invalidation, and Shadow eligibility." /><div className="evidence-ledger">{themes.map((theme) => { const cert = certificates[theme.theme_id]; return <article key={theme.theme_id}><div><span className="ticker">{theme.tracker_etf}</span><h2>{theme.display_name}</h2></div><div><span>Direction</span><strong>{cert?.direction.model_estimated ? cert.direction.state : "Not estimated"}</strong></div><div><span>Conflict</span><strong>{cert?.observer_agreement.conflict_count ?? 0}</strong></div><div><span>Next probe</span><strong>{cert?.next_probe.expected_information_value ?? "high"}</strong></div><button className="icon-button" onClick={() => cert && onEvidence(cert)} aria-label={`Open ${theme.display_name} evidence`} title="Open evidence"><ChevronRight /></button></article>; })}</div></>;
}

function CertificatesPage({ themes, certificates, selected, onSelect, onEvidence }: { themes: Theme[]; certificates: Record<string, Certificate>; selected: string; onSelect: (id: string) => void; onEvidence: () => void }) {
  const cert = certificates[selected];
  const theme = themes.find((item) => item.theme_id === selected);
  if (!cert || !theme) return <EmptyState title="Certificate unavailable" detail="No structured certificate exists for this theme." />;
  const copy = async () => navigator.clipboard.writeText(JSON.stringify(cert, null, 2));
  return <><SectionHeader eyebrow="Structured, immutable interpretation" title="Certificates" detail="Narrative text is rendered from the certificate and cannot change its evidence state." /><div className="certificate-toolbar"><label>Theme<select value={selected} onChange={(event) => onSelect(event.target.value)}>{themes.map((item) => <option key={item.theme_id} value={item.theme_id}>{item.display_name}</option>)}</select></label><button className="icon-text-button" onClick={copy}><Clipboard /> Copy</button><button className="icon-text-button" onClick={() => downloadJson(`${selected}-certificate.json`, cert)}><Download /> JSON</button><button className="icon-text-button" onClick={() => window.print()}><FileJson /> Print</button></div><article className="certificate-document"><header><div><p className="eyebrow">{theme.tracker_etf} · {cert.evidence_grade}</p><h2>{cert.decision_status.replaceAll("_", " ")}</h2></div><span>{cert.as_of_utc}</span></header><section><h3>Why</h3>{cert.facts.map((fact) => <p key={fact.text}>{fact.text}</p>)}</section><section><h3>Why not stronger</h3><p>Direction and Transmission inputs were captured, but no signed model state has been estimated or validated.</p></section><section><h3>What would change my mind</h3><ul>{cert.invalidation.map((item) => <li key={item}>{item}</li>)}</ul></section><section><h3>Next most valuable observation</h3><p>{cert.next_probe.acquire}</p><small>{cert.next_probe.reason}</small></section><section><h3>Eligible playbooks</h3><p>{cert.eligible_playbooks.join(", ")}</p></section><section><h3>Blocked actions</h3><p>Theme ETF, Theme Basket, torque overlay, paper positions, and real orders.</p></section><button className="command-button" onClick={onEvidence}>Inspect lineage <Network /></button></article></>;
}

function ExperimentsPage({ experiments }: { experiments: Experiment[] }) {
  const rows = [
    ["Day 0B", "Partial rehearsal", "Infrastructure", "Pass, does not count"],
    ["Full-day rehearsal", "Not started", "Infrastructure", "Blocked"],
    ["Data Shadow", "0 / 20", "Prospective", "Collecting not started"],
    ["Direction", "Not started", "Model Shadow", "Gate closed"],
    ["Direction + Transmission", "Not started", "Ablation", "Gate closed"],
    ["D + T + Episode", "Not started", "Ablation", "Gate closed"],
    ["D + T + E + Playbook", "Not started", "Ablation", "Gate closed"],
    ["Vehicle overlay", "Not started", "Ablation", "Gate closed"],
    ["Model Shadow", "Not started", "Prospective", "Gate closed"],
  ];
  return <><SectionHeader eyebrow="Evidence program" title="Experiments" detail="Progress is reported by evidence grade and preregistered gate, never promoted by interim performance." /><div className="table-actions"><button className="icon-text-button" onClick={() => downloadCsv("experiments.csv", rows.map(([name,status,grade,gate]) => ({ name,status,grade,gate })))}><Download /> CSV</button></div><div className="data-table" role="table" aria-label="Experiment program"><div role="row" className="table-head"><span>Name</span><span>Status</span><span>Evidence grade</span><span>Gate</span></div>{rows.map((row) => <div role="row" key={row[0]}>{row.map((cell) => <span key={cell}>{cell}</span>)}</div>)}</div>{experiments[0] && <aside className="experiment-note"><AlertTriangle /><p>{experiments[0].interpretation_boundary?.[0] ?? "Data readiness is not signed Direction."}</p></aside>}</>;
}

function DataQualityPage({ status, themes }: { status: Status; themes: Theme[] }) {
  const metrics = [
    ["Planned records", "740"], ["Captured", "666"], ["Missed", "74"], ["Future timestamps", "0"], ["Backfill", "0"], ["WebSocket reconnect", "0"], ["Ticker coverage", "100%"], ["Theme coverage", "6 / 6"],
  ];
  return <><SectionHeader eyebrow="Collection integrity" title="Data Quality" detail="The latest published rehearsal proves the afternoon chain only. Missing observations remain missing." /><div className="quality-grid">{metrics.map(([label,value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><section className="content-band"><div className="band-header"><div><h2>Theme coverage</h2><p>Readiness at 15:45 ET</p></div><StatusBadge label="PARTIAL REHEARSAL" state="warning" /></div><div className="coverage-list">{themes.map((theme) => <div key={theme.theme_id}><span>{theme.display_name}</span><progress max="100" value="100">100%</progress><strong>100%</strong></div>)}</div></section><section className="health-callout"><Gauge /><div><h2>Runtime health</h2><p>Collector checks passed in the Day 0B artifact. Scheduled task is not installed and formal Data Shadow has not started.</p></div><StatusBadge label={status.formal_data_shadow_started ? "RUNNING" : "NOT STARTED"} state="neutral" /></section></>;
}

function MethodologyPage() { return <><SectionHeader eyebrow="Evidence before action" title="Methodology" detail="The Observatory separates factual completeness, estimated state, and decision eligibility." /><div className="prose-grid"><section><h2>Point in time</h2><p>Every observation carries event, observed, and maximum-data timestamps. A missed scheduled point is never reconstructed.</p></section><section><h2>Observer separation</h2><p>Direction, Transmission, Episode, structural attention, and Fragility are independent estimates with explicit conflicts.</p></section><section><h2>Decision sufficiency</h2><p>No action is eligible unless the certificate has enough timely evidence and all relevant invalidations remain clear.</p></section><section><h2>Prospective validation</h2><p>Data Shadow precedes Model Shadow. Thresholds remain frozen during evaluation and costs remain part of the objective.</p></section></div></>; }
function ResearchPage() { return <><SectionHeader eyebrow="Disabled by default" title="Research" detail="Complex modules remain removable labs until they provide reproducible incremental value." /><div className="research-list">{[["Graph SSM","Disabled","Must beat the transparent baseline out of sample."],["Field models","Disabled","No activation without independent validation."],["Semantic event observer","Disabled","Known-at event timing must be reliable first."],["Torque overlay","Disabled","High beta alone is not a qualification mechanism."]].map(([name,status,detail]) => <article key={name}><Beaker /><div><h2>{name}</h2><p>{detail}</p></div><StatusBadge label={status.toUpperCase()} state="neutral" /></article>)}</div></>; }
function StatusPage({ status }: { status: Status }) { return <><SectionHeader eyebrow="Public system state" title="Status" detail="A concise record of what is running, what is blocked, and what cannot occur." /><div className="status-board"><section><h2>Runtime</h2><dl><div><dt>Mode</dt><dd>{status.mode}</dd></div><div><dt>Formal Data Shadow</dt><dd>{String(status.formal_data_shadow_started)}</dd></div><div><dt>Model Shadow</dt><dd>{String(status.model_shadow_started)}</dd></div></dl></section><section><h2>Evidence gates</h2><dl><div><dt>Data ready</dt><dd>{String(status.data_ready)}</dd></div><div><dt>Model estimated</dt><dd>{String(status.model_estimated)}</dd></div><div><dt>Decision eligible</dt><dd>{String(status.decision_eligible)}</dd></div></dl></section><section><h2>Prohibited outputs</h2><dl><div><dt>Paper positions</dt><dd>{status.paper_positions}</dd></div><div><dt>Real orders</dt><dd>{status.real_orders}</dd></div><div><dt>Live advice</dt><dd>Disabled</dd></div></dl></section></div></>; }

export default function App() {
  const [route, setRoute] = useState<Route>(routeFromHash());
  const [status, setStatus] = useState<Status | null>(null);
  const [themes, setThemes] = useState<Theme[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [certificates, setCertificates] = useState<Record<string, Certificate>>({});
  const [error, setError] = useState<string | null>(null);
  const [zone, setZone] = useState<"ET" | "UTC">("ET");
  const [themeFilter, setThemeFilter] = useState("all");
  const [range, setRange] = useState("latest");
  const [stateFilter, setStateFilter] = useState("all");
  const [menuOpen, setMenuOpen] = useState(false);
  const [drawer, setDrawer] = useState<Certificate | null>(null);
  const [now, setNow] = useState(new Date());

  const handleHash = useCallback(() => { setRoute(routeFromHash()); setMenuOpen(false); }, []);
  useEffect(() => { window.addEventListener("hashchange", handleHash); return () => window.removeEventListener("hashchange", handleHash); }, [handleHash]);
  useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 1000); return () => window.clearInterval(timer); }, []);
  useEffect(() => {
    Promise.all([loadStatus(), loadThemes(), loadExperiments()]).then(async ([nextStatus, nextThemes, nextExperiments]) => {
      setStatus(nextStatus); setThemes(nextThemes); setExperiments(nextExperiments);
      const entries = await Promise.all(nextThemes.map(async (theme) => [theme.theme_id, await loadCertificate(theme.theme_id)] as const));
      setCertificates(Object.fromEntries(entries));
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Public data could not be loaded"));
  }, []);

  const filteredThemes = useMemo(() => themes.filter((theme) => {
    if (themeFilter !== "all" && theme.theme_id !== themeFilter) return false;
    const certificate = certificates[theme.theme_id];
    if (stateFilter === "blocked") return certificate?.decision_status.includes("BLOCKED") ?? false;
    if (stateFilter === "ready") return certificate?.direction.data_ready ?? false;
    return true;
  }), [certificates, stateFilter, themeFilter, themes]);
  const selectedTheme = themeFromHash();
  const certificateSelection = selectedTheme ?? themes[0]?.theme_id ?? "semiconductors";

  if (error) return <main className="fatal-state"><AlertTriangle /><h1>Public state unavailable</h1><p>{error}</p><button onClick={() => window.location.reload()}>Retry</button></main>;
  if (!status || themes.length === 0 || Object.keys(certificates).length === 0) return <main className="loading-state" aria-busy="true"><div className="skeleton wide" /><div className="skeleton" /><div className="skeleton" /><span>Loading public evidence state</span></main>;

  const navigate = (next: Route, theme?: string) => routeTo(next, theme);
  const content = route === "today" ? <TodayPage status={status} themes={filteredThemes} certificates={certificates} onOpenTheme={(id) => navigate("themes", id)} onEvidence={setDrawer} zone={zone} />
    : route === "themes" ? <ThemesPage themes={filteredThemes} certificates={certificates} selectedTheme={selectedTheme} onSelect={(id) => navigate("themes", id)} onEvidence={setDrawer} />
    : route === "evidence" ? <EvidencePage themes={filteredThemes} certificates={certificates} onEvidence={setDrawer} />
    : route === "certificates" ? <CertificatesPage themes={themes} certificates={certificates} selected={certificateSelection} onSelect={(id) => navigate("certificates", id)} onEvidence={() => setDrawer(certificates[certificateSelection])} />
    : route === "experiments" ? <ExperimentsPage experiments={experiments} />
    : route === "data-quality" ? <DataQualityPage status={status} themes={filteredThemes} />
    : route === "methodology" ? <MethodologyPage />
    : route === "research" ? <ResearchPage />
    : <StatusPage status={status} />;

  return <div className="app-shell">
    <header className="app-header">
      <a className="brand" href="#/today"><span className="brand-mark">MS</span><span>Market State Observatory</span></a>
      <nav className={menuOpen ? "main-nav open" : "main-nav"} aria-label="Primary navigation">{nav.map(([id,label]) => <a key={id} href={`#/${id}`} className={route === id ? "active" : ""} aria-current={route === id ? "page" : undefined}>{label}</a>)}</nav>
      <div className="header-status"><span className="health-dot" aria-hidden="true" /> Healthy <time>{formatTime(now, zone)}</time></div>
      <button className="icon-button menu-button" onClick={() => setMenuOpen(!menuOpen)} aria-expanded={menuOpen} aria-label="Toggle navigation">{menuOpen ? <X /> : <Menu />}</button>
    </header>
    <aside className="filter-bar" aria-label="Global filters">
      <Filter aria-hidden="true" />
      <label>Theme<select value={themeFilter} onChange={(event) => setThemeFilter(event.target.value)}><option value="all">All themes</option>{themes.map((theme) => <option key={theme.theme_id} value={theme.theme_id}>{theme.display_name}</option>)}</select></label>
      <label>Range<select value={range} onChange={(event) => setRange(event.target.value)}><option value="latest">Latest</option><option value="day">Session</option><option value="20d">20-day gate</option></select></label>
      <label>State<select value={stateFilter} onChange={(event) => setStateFilter(event.target.value)}><option value="all">All states</option><option value="blocked">Blocked</option><option value="ready">Data ready</option></select></label>
      <div className="segmented" aria-label="Time zone"><button className={zone === "ET" ? "active" : ""} onClick={() => setZone("ET")}>ET</button><button className={zone === "UTC" ? "active" : ""} onClick={() => setZone("UTC")}>UTC</button></div>
    </aside>
    <main id="main" tabIndex={-1}>{content}</main>
    <footer className="site-footer"><div><strong>Market State Observatory</strong><p>Auditable evidence states. No trading advice.</p></div><div><a href="#/methodology">Methodology</a><a href="#/status">System status</a><a href="https://github.com/yuhanyu0/market-state-observatory">GitHub</a></div></footer>
    <nav className="mobile-nav" aria-label="Mobile navigation">{nav.slice(0, 5).map(([id,label,Icon]) => <a key={id} href={`#/${id}`} className={route === id ? "active" : ""}><Icon /><span>{label}</span></a>)}</nav>
    {drawer && <EvidenceDrawer certificate={drawer} onClose={() => setDrawer(null)} />}
  </div>;
}
