import { describe, expect, it } from 'vitest';
import { auditFieldChanges } from './audit-fields';

// SUPPLIER-COST-ACCESS: the server replaces a cost value with "hidden" for a reader without
// `products.cost.view` and names the field in `masked_fields`.
describe('audit field changes: masked cost fields', () => {
  it('says the cost changed without a value', () => {
    const lines = auditFieldChanges(
      { cost_price: 'hidden', product_name: 'Old sink' },
      { cost_price: 'hidden', product_name: 'New sink' },
      ['cost_price'],
    );
    expect(lines.map((l) => (l.kind === 'line' ? l.text : l.label))).toEqual([
      'Cost price changed (values hidden)',
      'Product name: Old sink → New sink',
    ]);
  });

  it('shows the values to a reader who was not masked', () => {
    const lines = auditFieldChanges({ cost_price: '120.00' }, { cost_price: '125.00' }, null);
    expect(lines.map((l) => (l.kind === 'line' ? l.text : l.label))).toEqual([
      'Cost price: 120.00 → 125.00',
    ]);
  });
});
