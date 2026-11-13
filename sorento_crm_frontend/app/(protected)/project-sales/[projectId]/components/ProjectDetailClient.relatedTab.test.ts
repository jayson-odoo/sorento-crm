/**
 * PROJECT-RELATED-RECORDS AC-A1, AC-A2: the project page has a "Related" tab where "Sponsorship
 * Form" was, in the same position, and the old `?tab=sponsorships` link opens it.
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import * as client from './ProjectDetailClient';

const tabs = () =>
  (client as unknown as { TABS: ReadonlyArray<{ id: string; label: string }> }).TABS;

describe('project detail Related tab', () => {
  it('AC-A1 Related sits where Sponsorship Form was', () => {
    const ids = tabs().map((t) => t.id);
    const at = ids.indexOf('related');
    expect(at, 'a tab with id "related"').toBe(4);
    expect(tabs()[at].label).toBe('Related');
    expect(ids).not.toContain('sponsorships');
    expect(tabs().map((t) => t.label)).not.toContain('Sponsorship Form');
    expect(ids[at - 1]).toBe('sample-requests');
    expect(ids[at + 1]).toBe('orders');
  });

  it('AC-A2 ?tab=sponsorships opens Related', () => {
    expect(client.resolveProjectTab('sponsorships')).toBe('related');
    expect(client.resolveProjectTab('related')).toBe('related');
  });
});
