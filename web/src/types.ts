export type Theme = {
  theme_id: string;
  display_name: string;
  tracker_etf: string;
  benchmark: string;
  constituents: string[];
  status: string;
};

export type CertificateLayer = {
  state: string;
  eligible: boolean;
  data_ready: boolean;
  model_estimated: boolean;
  decision_eligible: boolean;
  uncertainty: number | null;
  evidence_refs: string[];
  metrics: Record<string, unknown>;
  invalidation: string;
};

export type Certificate = {
  certificate_id: string;
  theme_id: string;
  as_of_utc: string;
  evidence_grade: string;
  facts: { kind: string; text: string }[];
  direction: CertificateLayer;
  transmission: CertificateLayer;
  episode: CertificateLayer;
  structural_attention: CertificateLayer;
  fragility: CertificateLayer;
  observer_agreement: { score: number; estimated_observers: number; conflict_count: number; state: string };
  observer_conflicts: unknown[];
  uncertainty: number;
  invalidation: string[];
  next_probe: { acquire: string; reason: string; deadline_utc: string; expected_information_value: string };
  eligible_playbooks: string[];
  vehicle_eligibility: Record<string, boolean>;
  decision_status: string;
};

export type Status = {
  updated_at: string;
  mode: string;
  data_ready: boolean;
  model_estimated: boolean;
  decision_eligible: boolean;
  formal_data_shadow_started: boolean;
  model_shadow_started: boolean;
  data_shadow_gate: { valid_days: number; required_days: number };
  paper_positions: number;
  real_orders: number;
  next_milestone: string;
  day0b: Record<string, unknown>;
};

export type Experiment = {
  experiment_id: string;
  status: string;
  counts_toward_20_day_gate: boolean;
  captured_valid_records: number;
  planned_records: number;
  trading_date: string;
  interpretation_boundary: string[];
};
