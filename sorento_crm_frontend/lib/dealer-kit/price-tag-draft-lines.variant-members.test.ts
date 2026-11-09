/**
 * PRICETAG-UPGRADE-VARIANTS review fix round 1, item 2 (FE half): when the members lookup answers,
 * an unticked id that is no longer a member is dropped, so a stale id never blocks a save with
 * NOT_A_VARIANT (the chooser cannot show it to clear it).
 */
import { describe, expect, it } from 'vitest';

import { emptyDraftLine, withVariantMembers, type DraftLine } from './price-tag-draft-lines';

const member = (id: string, list = 1750) => ({
  product_id: id,
  code: id.toUpperCase(),
  name: id,
  list_price: list,
  is_discontinued: false,
});

const line = (excluded: string[]): DraftLine => ({
  ...emptyDraftLine(),
  key: 'l1',
  product_id: 'p1',
  code: 'SRTWC8354-SH',
  excluded_variant_ids: excluded,
});

describe('withVariantMembers', () => {
  it('stores the members, the product they answer for and the own list price', () => {
    const out = withVariantMembers(line([]), 'p1', { members: [member('a')], own_list_price: 1600 });
    expect(out.variant_members).toEqual([member('a')]);
    expect(out.variant_members_for).toBe('p1');
    expect(out.own_list_price).toBe(1600);
  });

  it('keeps unticked ids that are still members', () => {
    const out = withVariantMembers(line(['a', 'b']), 'p1', {
      members: [member('a'), member('b'), member('c')],
      own_list_price: 1750,
    });
    expect(out.excluded_variant_ids).toEqual(['a', 'b']);
  });

  it('drops an unticked id that left the family since', () => {
    const out = withVariantMembers(line(['gone', 'b']), 'p1', {
      members: [member('a'), member('b')],
      own_list_price: 1750,
    });
    expect(out.excluded_variant_ids).toEqual(['b']);
  });

  it('a product with no members left clears the list', () => {
    const out = withVariantMembers(line(['a']), 'p1', { members: [], own_list_price: 1750 });
    expect(out.excluded_variant_ids).toEqual([]);
  });
});
