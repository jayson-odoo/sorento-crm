/** F1: MY WORK > Dealer access, a salesperson item gated by the own-contact edit slug. */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR } from './menu.config';

describe('MENU_SIDEBAR - Dealer access entry', () => {
  it('sits under MY WORK as a salesperson item with the edit_own permission', () => {
    const myWork = MENU_SIDEBAR.findIndex((i) => i.heading === 'MY WORK');
    const myRequests = MENU_SIDEBAR.findIndex((i) => i.heading === 'MY REQUESTS');
    const at = MENU_SIDEBAR.findIndex((i) => i.title === 'Dealer access');
    expect(at).toBeGreaterThan(myWork);
    expect(at).toBeLessThan(myRequests);
    expect(MENU_SIDEBAR[at]).toMatchObject({
      path: '/sales/dealer-access',
      permission: 'user_management.contacts.edit_own',
      audience: 'salesperson',
    });
  });
});
