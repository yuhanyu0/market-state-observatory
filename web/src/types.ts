import { z } from "zod";

export const themeSchema = z.object({
  theme_id: z.string(), display_name: z.string(), tracker_etf: z.string(), benchmark: z.string(),
  constituents: z.array(z.string()), status: z.string(),
});

export const certificateLayerSchema = z.object({
  state: z.string(), eligible: z.boolean(), data_ready: z.boolean(), model_estimated: z.boolean(),
  decision_eligible: z.boolean(), uncertainty: z.number().nullable(), evidence_refs: z.array(z.string()),
  metrics: z.record(z.unknown()), invalidation: z.string().nullable(),
});

export const certificateSchema = z.object({
  certificate_id: z.string(), theme_id: z.string(), as_of_utc: z.string().datetime({ offset: true }),
  evidence_grade: z.string(), facts: z.array(z.object({ kind: z.string(), text: z.string() })),
  direction: certificateLayerSchema, transmission: certificateLayerSchema, episode: certificateLayerSchema,
  structural_attention: certificateLayerSchema, fragility: certificateLayerSchema,
  observer_agreement: z.object({ score: z.number(), estimated_observers: z.number().int(), conflict_count: z.number().int(), state: z.string() }),
  observer_conflicts: z.array(z.unknown()), uncertainty: z.number().nullable(), invalidation: z.array(z.string()),
  next_probe: z.object({ acquire: z.string(), reason: z.string(), deadline_utc: z.string(), expected_information_value: z.string() }),
  eligible_playbooks: z.array(z.string()), vehicle_eligibility: z.record(z.boolean()), decision_status: z.string(),
});

const timelineItemSchema = z.object({
  name: z.string(), scheduled_at: z.string().datetime({ offset: true }),
  status: z.enum(["captured", "missed", "pending", "failed"]), evidence_at: z.string().datetime({ offset: true }).nullable(),
});

export const statusSchema = z.object({
  schema_version: z.literal("market-state-observatory-status-v0.4.1"),
  updated_at: z.string().datetime({ offset: true }), trading_date: z.string(),
  last_evidence_at: z.string().datetime({ offset: true }), snapshot_evidence_grade: z.string(),
  snapshot_kind: z.enum(["synthetic", "rehearsal", "formal", "model_shadow"]),
  health_state: z.enum(["HEALTHY", "STALE", "DEGRADED", "FAILED"]), runtime_phase: z.string(),
  next_event: z.object({ name: z.string(), scheduled_at: z.string().datetime({ offset: true }) }).nullable(),
  timeline: z.array(timelineItemSchema), action_required: z.string(), live_trading_enabled: z.literal(false),
  formal_data_shadow_started: z.boolean(), model_shadow_started: z.boolean(), paper_positions: z.literal(0), real_orders: z.literal(0),
  data_ready: z.boolean(), model_estimated: z.boolean(), decision_eligible: z.boolean(),
  data_shadow_gate: z.object({ valid_days: z.number().int().nonnegative(), required_days: z.number().int().positive() }),
  quality: z.object({
    planned: z.number().int().nonnegative(), captured: z.number().int().nonnegative(), missed: z.number().int().nonnegative(),
    future_timestamps: z.number().int().nonnegative(), backfill: z.number().int().nonnegative(), websocket_reconnects: z.number().int().nonnegative(),
    ticker_coverage: z.number().min(0).max(1), theme_coverage: z.number().int().nonnegative(), missing_tickers: z.array(z.string()),
  }), next_milestone: z.string(),
});

export const experimentSchema = z.object({
  experiment_id: z.string(), status: z.string(), counts_toward_20_day_gate: z.boolean(),
  captured_valid_records: z.number().int().nonnegative(), planned_records: z.number().int().nonnegative(),
  trading_date: z.string(), interpretation_boundary: z.array(z.string()), schema_version: z.string(),
});

export type Theme = z.infer<typeof themeSchema>;
export type CertificateLayer = z.infer<typeof certificateLayerSchema>;
export type Certificate = z.infer<typeof certificateSchema>;
export type Status = z.infer<typeof statusSchema>;
export type Experiment = z.infer<typeof experimentSchema>;
