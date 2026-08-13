import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import type { Certificate } from "../types";

type Props = { certificate: Certificate; onClose: () => void };

export function EvidenceDrawer({ certificate, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside className="evidence-drawer" role="dialog" aria-modal="true" aria-labelledby="evidence-title" onMouseDown={(e) => e.stopPropagation()}>
        <header>
          <div><p className="eyebrow">Evidence lineage</p><h2 id="evidence-title">{certificate.theme_id}</h2></div>
          <button ref={closeRef} className="icon-button" onClick={onClose} aria-label="Close evidence drawer" title="Close"><X /></button>
        </header>
        <dl className="detail-list">
          <div><dt>Observer</dt><dd>Structured State Certificate compiler</dd></div>
          <div><dt>Timestamp</dt><dd>{certificate.as_of_utc}</dd></div>
          <div><dt>Evidence grade</dt><dd>{certificate.evidence_grade}</dd></div>
          <div><dt>Model version</dt><dd>mso-certificate-v0.4</dd></div>
          <div><dt>Uncertainty</dt><dd>{certificate.uncertainty.toFixed(2)}</dd></div>
          <div><dt>Threshold source</dt><dd>Frozen structured contract</dd></div>
          <div><dt>Counts toward Shadow</dt><dd>No, synthetic public reference</dd></div>
        </dl>
        <section><h3>Raw fact summary</h3>{certificate.facts.map((fact) => <p key={fact.text}>{fact.text}</p>)}</section>
        <section><h3>Source lineage</h3><code>{certificate.direction.evidence_refs.join("\n")}</code></section>
        <section><h3>Invalidation</h3><ul>{certificate.invalidation.map((item) => <li key={item}>{item}</li>)}</ul></section>
      </aside>
    </div>
  );
}
