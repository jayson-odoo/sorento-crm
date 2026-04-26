function newId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `id-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export const QUOTATION_PACKAGE_TEMPLATES_KEY = 'quotation_package_templates';

export type QuotationLine = {
  id: string;
  product_id?: string;
  product_code?: string;
  name: string;
  description: string;
  quantity: number;
  uom: string;
};

export type QuotationPackageTemplate = {
  id: string;
  name: string;
  validity_days: number;
  terms: string;
  items: QuotationLine[];
};

export const DEFAULT_QUOTATION_TEMPLATES: QuotationPackageTemplate[] = [
  {
    id: 'demo-office',
    name: 'Office Furniture Package',
    validity_days: 30,
    terms: 'Payment terms: 50% deposit, 50% upon delivery. Delivery within 4 weeks.',
    items: [
      {
        id: 'l1',
        name: 'Executive Desk',
        description: 'Premium wooden executive desk with drawers',
        quantity: 1,
        uom: 'Unit',
      },
      {
        id: 'l2',
        name: 'Office Chair',
        description: 'Ergonomic office chair with lumbar support',
        quantity: 1,
        uom: 'Unit',
      },
    ],
  },
];

export function parseQuotationTemplates(raw: unknown): QuotationPackageTemplate[] {
  if (!Array.isArray(raw)) return [];
  const out: QuotationPackageTemplate[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const o = item as Record<string, unknown>;
    const id = String(o.id ?? '').trim() || newId();
    const name = String(o.name ?? '').trim();
    if (!name) continue;
    const validity_days =
      typeof o.validity_days === 'number'
        ? o.validity_days
        : Number.parseInt(String(o.validity_days ?? '30'), 10) || 30;
    const terms = String(o.terms ?? '').trim();
    const itemsRaw = o.items;
    const items: QuotationLine[] = [];
    if (Array.isArray(itemsRaw)) {
      for (const line of itemsRaw) {
        if (!line || typeof line !== 'object') continue;
        const L = line as Record<string, unknown>;
        const lid = String(L.id ?? '').trim() || newId();
        const lname = String(L.name ?? L.item ?? '').trim();
        if (!lname) continue;
        items.push({
          id: lid,
          product_id: String(L.product_id ?? '').trim() || undefined,
          product_code: String(L.product_code ?? '').trim() || undefined,
          name: lname,
          description: String(L.description ?? '').trim(),
          quantity: typeof L.quantity === 'number' ? L.quantity : Number(L.quantity) || 0,
          uom: String(L.uom ?? 'Unit').trim() || 'Unit',
        });
      }
    }
    out.push({ id, name, validity_days, terms, items });
  }
  return out;
}
