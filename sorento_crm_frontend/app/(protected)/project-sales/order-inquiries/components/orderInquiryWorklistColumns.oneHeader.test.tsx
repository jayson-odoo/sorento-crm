/**
 * AC-OH-01 (`oi-worklist-one-header-acceptance-criteria.md`, S6): the worklist's Order
 * inquiry column (`inquiry_no`) is hidden on first load with no saved column preference -
 * the number stays on the header, the email and the URL (R5), never a default-visible
 * column purchasing has to hide by hand every time.
 *
 * TEST-FIRST: `orderInquiryWorklistColumns.tsx` exports no default-hidden set today (the
 * plan's own measured fact - `OrderInquiriesClient.tsx` carries no `columnVisibility`
 * state at all), so this fails on import until the coder adds the named export below.
 * Asserted on the export rather than a full client mount, so the test does not depend on
 * how the client wires the DataGrid's `initialState` - only on the CONTRACT the client
 * reads it from.
 */
import { describe, expect, it } from 'vitest';
import { DEFAULT_HIDDEN_COLUMNS } from './orderInquiryWorklistColumns';

describe('AC-OH-01: the Order inquiry column is hidden by default', () => {
  it('lists inquiry_no in the default-hidden column set', () => {
    expect(DEFAULT_HIDDEN_COLUMNS).toContain('inquiry_no');
  });
});
