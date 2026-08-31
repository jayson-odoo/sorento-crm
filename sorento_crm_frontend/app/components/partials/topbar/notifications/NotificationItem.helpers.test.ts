import { describe, it, expect } from 'vitest';
import { toInternalPath, collectLinks, primaryLink } from './NotificationItem';
import type { NotificationItem } from '@/services/notificationService';

function makeItem(overrides: Partial<NotificationItem> = {}): NotificationItem {
  return {
    id: 'notif-1',
    user_id: 'user-1',
    type: 'sla_alert',
    title: 'Test notification',
    body: null,
    data: null,
    read_at: null,
    archived_at: null,
    resolved_at: null,
    created_at: '2026-08-31T00:00:00',
    source_entity_type: null,
    source_entity_id: null,
    event_type: null,
    ...overrides,
  };
}

describe('toInternalPath', () => {
  it('returns a relative path as-is', () => {
    expect(toInternalPath('/ticket-management/tickets/abc-123')).toBe(
      '/ticket-management/tickets/abc-123',
    );
  });

  it('resolves an absolute same-origin URL to a path', () => {
    // jsdom's default test origin is http://localhost:3000
    expect(toInternalPath('http://localhost:3000/ticket-management/tickets/abc-123?tab=notes')).toBe(
      '/ticket-management/tickets/abc-123?tab=notes',
    );
  });

  it('returns null for an absolute foreign-origin URL', () => {
    expect(toInternalPath('https://chat.respond.io/some/thread')).toBeNull();
  });

  it('returns null for a malformed URL', () => {
    expect(toInternalPath('not a url')).toBeNull();
  });
});

describe('collectLinks', () => {
  it('trims trailing sentence punctuation off a body URL', () => {
    const item = makeItem({
      body: 'Open: http://localhost:3000/?ticket=ABC-1.',
    });
    expect(collectLinks(item)).toEqual(['http://localhost:3000/?ticket=ABC-1']);
  });

  it('collects data.link, data.url, and body URLs in that order', () => {
    const item = makeItem({
      data: { link: '/a/b', url: 'https://chat.respond.io/x' },
      body: 'See http://localhost:3000/c/d as well.',
    });
    expect(collectLinks(item)).toEqual([
      '/a/b',
      'https://chat.respond.io/x',
      'http://localhost:3000/c/d',
    ]);
  });

  it('returns an empty array when there is nothing to link to', () => {
    expect(collectLinks(makeItem())).toEqual([]);
  });
});

describe('primaryLink', () => {
  it('prefers an in-app link over an external one, regardless of order in the body', () => {
    const item = makeItem({
      body:
        'Chat: https://chat.respond.io/thread/xyz Open: http://localhost:3000/?ticket=SLA-42',
    });
    expect(primaryLink(item)).toBe('http://localhost:3000/?ticket=SLA-42');
  });

  it('falls back to the first external link when nothing is internal', () => {
    const item = makeItem({
      body: 'Chat: https://chat.respond.io/thread/xyz',
    });
    expect(primaryLink(item)).toBe('https://chat.respond.io/thread/xyz');
  });

  it('returns null when there are no links at all', () => {
    expect(primaryLink(makeItem())).toBeNull();
  });
});
