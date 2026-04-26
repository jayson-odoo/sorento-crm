/** Lead qualification lists stored under process settings `assignment` (plus optional metadata fields). */

export type LeadRefItem = {
  code: string;
  label: string;
  is_active: boolean;
  sort_order?: number;
  /** For `lead_states`: country code (matches `lead_countries[].code`). */
  country_code?: string;
};

export function parseLeadRefItems(raw: unknown): LeadRefItem[] {
  if (!Array.isArray(raw)) return [];
  const out: LeadRefItem[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const o = item as Record<string, unknown>;
    const code = String(o.code ?? '').trim();
    if (!code) continue;
    const label = String(o.label ?? o.name ?? code).trim() || code;
    const is_active = o.is_active === undefined ? true : Boolean(o.is_active);
    const sort_order =
      typeof o.sort_order === 'number'
        ? o.sort_order
        : typeof o.order === 'number'
          ? o.order
          : undefined;
    const country_code =
      o.country_code !== undefined && o.country_code !== null ? String(o.country_code).trim() : undefined;
    out.push({
      code,
      label,
      is_active,
      ...(sort_order !== undefined ? { sort_order } : {}),
      ...(country_code ? { country_code } : {}),
    });
  }
  return out;
}

export function toAssignmentPayload(rows: LeadRefItem[]): Record<string, unknown>[] {
  return rows
    .filter((r) => r.code.trim())
    .map((r) => {
      const x: Record<string, unknown> = {
        code: r.code.trim(),
        label: r.label.trim() || r.code.trim(),
        is_active: r.is_active,
      };
      if (r.sort_order !== undefined) x.sort_order = r.sort_order;
      if (r.country_code) x.country_code = r.country_code.trim();
      return x;
    });
}
