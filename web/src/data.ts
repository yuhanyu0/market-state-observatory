import type { Certificate, Experiment, Status, Theme } from "./types";

const dataUrl = (path: string) => `${import.meta.env.BASE_URL}data/${path}`;

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(dataUrl(path));
  if (!response.ok) throw new Error(`Public data unavailable: ${path}`);
  return response.json() as Promise<T>;
}

export const loadStatus = () => getJson<Status>("status.json");
export const loadThemes = async () => (await getJson<{ themes: Theme[] }>("themes.json")).themes;
export const loadCertificate = (themeId: string) => getJson<Certificate>(`certificates/${themeId}.json`);
export const loadExperiments = () => getJson<Experiment[]>("experiments.json");

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
