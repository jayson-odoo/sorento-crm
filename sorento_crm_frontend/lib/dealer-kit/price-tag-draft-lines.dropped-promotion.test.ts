/**
 * PRICETAG-DISCONTINUED-PICK round 3: the save drops a promotion a narrowed pick no longer
 * touches (server, `price_tag_request_service.py`); the form names those lines after the save.
 */
import { describe, expect, it } from 'vitest';

import { droppedPromotionNote } from './price-tag-draft-lines';

describe('droppedPromotionNote', () => {
  it('names each line whose sent promotion came back as none, 1-based, in line order', () => {
    const sent = [{ promotion_id: 'p1' }, { promotion_id: null }, { promotion_id: 'p3' }];
    const saved = [
      { promotion_id: null, sort_order: 0 },
      { promotion_id: null, sort_order: 1 },
      { promotion_id: null, sort_order: 2 },
    ];
    expect(droppedPromotionNote(sent, saved)).toBe(
      'Promotion removed from lines 1, 3: it does not cover the option picked.',
    );
  });

  it('reads the saved lines in their sort order, not the order they arrived in', () => {
    const sent = [{ promotion_id: 'p1' }, { promotion_id: 'p2' }];
    const saved = [
      { promotion_id: 'p2', sort_order: 1 },
      { promotion_id: null, sort_order: 0 },
    ];
    expect(droppedPromotionNote(sent, saved)).toBe(
      'Promotion removed from line 1: it does not cover the option picked.',
    );
  });

  it('says nothing when every sent promotion was kept or none was sent', () => {
    expect(droppedPromotionNote([{ promotion_id: 'p1' }], [{ promotion_id: 'p1', sort_order: 0 }])).toBeNull();
    expect(droppedPromotionNote([{ promotion_id: null }], [{ promotion_id: null, sort_order: 0 }])).toBeNull();
    expect(droppedPromotionNote([{ promotion_id: 'p1' }], undefined)).toBeNull();
  });
});
