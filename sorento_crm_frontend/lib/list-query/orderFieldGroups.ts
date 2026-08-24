import type { ListQueryFieldMeta } from '@/lib/list-query/listQueryService';

export type OrderFieldGroups = {
  order: ListQueryFieldMeta[];
  lineDirect: ListQueryFieldMeta[];
  product: ListQueryFieldMeta[];
  warehouse: ListQueryFieldMeta[];
};

/** Section for orders list-query fields (export + filter UI). */
export function inferOrderFieldSection(f: ListQueryFieldMeta): 'order' | 'line' {
  if (f.export_section === 'order' || f.export_section === 'line') return f.export_section;
  return f.is_line_field ? 'line' : 'order';
}

/** Subgroup under line: product / warehouse / none. */
export function inferOrderFieldSubgroup(f: ListQueryFieldMeta): 'product' | 'warehouse' | null {
  if (f.export_subgroup === 'product' || f.export_subgroup === 'warehouse') return f.export_subgroup;
  if (f.field_key.startsWith('line_product')) return 'product';
  if (f.field_key.startsWith('line_warehouse')) return 'warehouse';
  return null;
}

/** Shorter label inside nested Product / Warehouse groups. */
export function shortNestedOrderLineLabel(label: string, subgroup: 'product' | 'warehouse'): string {
  if (subgroup === 'product') {
    const s = label.replace(/^Line\s*[ -  - -]\s*product\s*/i, '').trim();
    return s || label;
  }
  const s = label.replace(/^Line\s*[ -  - -]\s*warehouse\s*/i, '').trim();
  return s || label;
}

export function groupOrderListFields(fields: ListQueryFieldMeta[]): OrderFieldGroups {
  const order: ListQueryFieldMeta[] = [];
  const lineDirect: ListQueryFieldMeta[] = [];
  const product: ListQueryFieldMeta[] = [];
  const warehouse: ListQueryFieldMeta[] = [];
  for (const f of fields) {
    const sec = inferOrderFieldSection(f);
    const sub = inferOrderFieldSubgroup(f);
    if (sec === 'order') order.push(f);
    else if (sub === 'product') product.push(f);
    else if (sub === 'warehouse') warehouse.push(f);
    else lineDirect.push(f);
  }
  return { order, lineDirect, product, warehouse };
}
