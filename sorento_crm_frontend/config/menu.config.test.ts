import { describe, expect, it } from 'vitest';

import { MENU_SIDEBAR } from './menu.config';

describe('MENU_SIDEBAR', () => {
  it('has no duplicate top-level group titles', () => {
    const titles = MENU_SIDEBAR.filter((item) => item.title && item.children).map(
      (item) => item.title,
    );
    const duplicates = titles.filter((title, index) => titles.indexOf(title) !== index);
    expect(duplicates).toEqual([]);
  });

  it('has exactly one Dealer Kit group', () => {
    const dealerKit = MENU_SIDEBAR.filter((item) => item.title === 'Dealer Kit');
    expect(dealerKit).toHaveLength(1);
  });
});
