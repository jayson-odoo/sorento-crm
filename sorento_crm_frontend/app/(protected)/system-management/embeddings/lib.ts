import type { WordHome } from './types/embeddings.types';

export const num = (n: number) => n.toLocaleString('en-US');

/** A score or floor as the resolver holds it, trailing zeros dropped ("0.6", "0.83"). */
export const score = (n: number) => String(Math.round(n * 1000) / 1000);

export const HOME_ORDER: WordHome[] = ['label', 'code', 'class', 'alias_column', 'alias_set', 'description'];

export const HOME_LABEL: Record<WordHome, string> = {
  label: 'Label',
  code: 'Code',
  class: 'Class',
  alias_column: 'Alias column',
  alias_set: 'Alias set',
  description: 'Description',
};

export const LIST_TABS: { value: string; label: string }[] = [
  { value: 'category', label: 'Category' },
  { value: 'file_type', label: 'File type' },
  { value: 'sales_channel', label: 'Sales channel' },
  { value: 'spec', label: 'Spec' },
  { value: 'brand', label: 'Brand' },
  { value: 'promotion_kind', label: 'Promotion kind' },
  { value: 'location', label: 'Location' },
  { value: 'salesperson', label: 'Salesperson' },
  { value: 'customer', label: 'Customer' },
];

/** The record sources as a person reads them ("product_spec" -> "Product spec"). */
export const sourceName = (source: string) => {
  const text = source.replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
};

/**
 * Arrow-key tab switching that takes effect on the key press itself (Radix moves focus a tick later and activates on
 * focus; this picks the same neighbour at once, so the view never lags the keyboard).
 */
export function arrowTabs(values: string[], current: string, change: (value: string) => void) {
  return (event: { key: string }) => {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (!step) return;
    const at = values.indexOf(current);
    change(values[(at + step + values.length) % values.length]);
  };
}
