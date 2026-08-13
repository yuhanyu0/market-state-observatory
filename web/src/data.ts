import { z } from "zod";
import {
  certificateSchema, experimentSchema, statusSchema, themeSchema,
  type Certificate, type Experiment, type Status, type Theme,
} from "./types";

const dataUrl = (path: string) => `${import.meta.env.BASE_URL}data/${path}`;

async function getJson<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  const response = await fetch(dataUrl(path));
  if (!response.ok) throw new Error(`Public data unavailable: ${path}`);
  const parsed = schema.safeParse(await response.json());
  if (!parsed.success) throw new Error(`Public state invalid: ${path}`);
  return parsed.data;
}

export const loadStatus = (): Promise<Status> => getJson("status.json", statusSchema);
export const loadThemes = async (): Promise<Theme[]> => (await getJson("themes.json", z.object({ themes: z.array(themeSchema) }))).themes;
export const loadCertificate = (themeId: string): Promise<Certificate> => getJson(`certificates/${themeId}.json`, certificateSchema);
export const loadExperiments = (): Promise<Experiment[]> => getJson("experiments.json", z.array(experimentSchema));

export function downloadJson(name: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  link.click();
  URL.revokeObjectURL(link.href);
}

export function downloadCsv(name: string, rows: Record<string, unknown>[]): void {
  const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  const quote = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const csv = [keys.map(quote).join(","), ...rows.map((row) => keys.map((key) => quote(row[key])).join(","))].join("\n");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  link.download = name;
  link.click();
  URL.revokeObjectURL(link.href);
}
