import { describe, expect, it } from 'vitest';
import { PurchaseRequestSchema } from './purchase-request-schema';

/** Total Project Value FE guard rail — mirrors backend validators.validate_project_value.
 *  Prevents regression of the "string saved as null" / Numeric(15,2) overflow bugs. */
function parseTPV(value: unknown) {
  return PurchaseRequestSchema.shape.total_project_value.safeParse(value);
}

describe('total_project_value validation', () => {
  it.each([1234, '1234', '1234.00', '0.5', null, '', '9999999999999.99'])(
    'accepts numeric / empty value: %s',
    (value) => {
      expect(parseTPV(value).success).toBe(true);
    },
  );

  it.each(['800K', 'abc', '1.6 mil'])('rejects non-numeric: %s', (value) => {
    const res = parseTPV(value);
    expect(res.success).toBe(false);
    if (!res.success) {
      expect(res.error.issues.some((i) => /must be a number/.test(i.message))).toBe(true);
    }
  });

  it.each(['10000000000000', '123446433232323232323232'])(
    'rejects out-of-range (>= 10^13): %s',
    (value) => {
      const res = parseTPV(value);
      expect(res.success).toBe(false);
      if (!res.success) {
        expect(res.error.issues.some((i) => /too large/.test(i.message))).toBe(true);
      }
    },
  );
});
