/** SPEC-SHEET-DESIGNER-PARITY A1: "Add accessory" shows a product code once. */
import { describe, expect, it } from 'vitest';

import { accessoryOptionsFor } from './ReaderPage';

const page = (key: string, code: string, name: string, picked: string[] = []) => ({
  key,
  code,
  name,
  picked,
  accessories: [] as never[],
});

describe('accessoryOptionsFor', () => {
  it('a product whose name is its code is listed by the code once', () => {
    const pages = [page('cover', '', 'Cover'), page('l1', 'SRT73-CR', 'SRT73-CR'), page('l2', 'CB310-CR-L', 'CB310-CR-L')];
    const options = accessoryOptionsFor(pages[1], pages);
    expect(options.map((o) => o.label)).toEqual(['CB310-CR-L']);
  });

  it('a name that says more than the code is kept after it', () => {
    const pages = [page('l1', 'SRT73-CR', 'SRT73-CR'), page('l2', 'AV-01', 'Angle valve chrome')];
    expect(accessoryOptionsFor(pages[0], pages).map((o) => o.label)).toEqual(['AV-01 Angle valve chrome']);
  });

  it('an accessory this page already picked is listed the same way', () => {
    const host = {
      ...page('l1', 'SRT73-CR', 'SRT73-CR', ['l2']),
      accessories: [{ key: 'l2', source: 'picked', code: 'FH-40', name: 'FH-40' }] as never[],
    };
    expect(accessoryOptionsFor(host, [host]).map((o) => o.label)).toEqual(['FH-40']);
  });
});
