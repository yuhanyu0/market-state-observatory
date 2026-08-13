import { ArrowRight, CircleHelp } from "lucide-react";
import type { Certificate, Theme } from "../types";
import { StatusBadge } from "./StatusBadge";

type Props = { theme: Theme; certificate?: Certificate; onOpen: () => void; onEvidence: () => void };

export function ThemeCard({ theme, certificate, onOpen, onEvidence }: Props) {
  const direction = certificate?.direction;
  return (
    <article className="theme-card">
      <header><div><p className="ticker">{theme.tracker_etf}</p><h3>{theme.display_name}</h3></div><StatusBadge label="DATA REHEARSAL" state="neutral" /></header>
      <dl className="state-grid">
        <div><dt>Data freshness</dt><dd>Aug 10, 15:45 ET</dd></div>
        <div><dt>Direction</dt><dd>{direction?.model_estimated ? direction.state : "Not estimated"}</dd></div>
        <div><dt>Transmission</dt><dd>{certificate?.transmission.model_estimated ? certificate.transmission.state : "Not estimated"}</dd></div>
        <div><dt>Episode</dt><dd>{certificate?.episode.state ?? "Unavailable"}</dd></div>
        <div><dt>Structural attention</dt><dd>{certificate?.structural_attention.state ?? "Unavailable"}</dd></div>
        <div><dt>Fragility</dt><dd>{certificate?.fragility.state ?? "Unknown"}</dd></div>
      </dl>
      <div className="card-notice"><CircleHelp aria-hidden="true" /><span>Input readiness is not a positive Direction estimate.</span></div>
      <p className="conflict-line">Observer conflict: {certificate?.observer_agreement.conflict_count ?? 0} detected</p>
      <p className="next-probe"><strong>Next probe</strong>{certificate?.next_probe.acquire ?? "Acquire the next legal point-in-time observation."}</p>
      <footer>
        <button className="text-button" onClick={onEvidence}>Evidence</button>
        <button className="command-button" onClick={onOpen}>Open theme <ArrowRight /></button>
      </footer>
    </article>
  );
}
