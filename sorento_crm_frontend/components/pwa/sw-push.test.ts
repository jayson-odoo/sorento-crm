/*
 * Tests for the push decision logic that lives in `public/sw.js`.
 *
 * The worker file is a classic service-worker script (it is served raw from
 * public/, never bundled), so it is loaded here through Node's CJS require
 * rather than the vite graph. `sw.js` exports its two pure-ish seams behind a
 * `typeof module !== 'undefined'` guard, which is inert inside a real worker.
 *
 * The test file sits here rather than beside sw.js because anything under
 * public/ is served to the internet by Next.
 *
 * Covers AC-M21 (coalesce), AC-M22 (suppress on a visible thread),
 * AC-M23 (show otherwise) from
 * documentation/plans/notifications/message-push-acceptance-criteria.md.
 */
import { createRequire } from 'node:module';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const requireCjs = createRequire(import.meta.url);
const sw = requireCjs('../../public/sw.js') as {
  parsePushPayload: (eventData: unknown) => Record<string, unknown>;
  handlePushPayload: (
    payload: Record<string, unknown>,
    ctx: { registration: unknown; clients: unknown },
  ) => Promise<{ shown: boolean; reason?: string }>;
};

const TRACKING_ID = '9f1c2d3e-4a5b-6c7d-8e9f-0a1b2c3d4e5f';
const CONTACT_ID = 'respond-77';
const TAG = `contact-${CONTACT_ID}`;

function messagePayload(
  link = `/sla-management/conversations?contact=${CONTACT_ID}`,
) {
  return {
    title: 'Ah Meng (Sorento Kitchen)',
    body: 'Can I get the price for the 900mm hood?',
    data: { link, tag: TAG },
  };
}

type FakeNotification = { tag: string; data: Record<string, unknown> };

function fakeRegistration(displayed: FakeNotification[] = []) {
  return {
    getNotifications: vi.fn(async ({ tag }: { tag?: string } = {}) =>
      displayed.filter((n) => !tag || n.tag === tag),
    ),
    showNotification: vi.fn(async () => undefined),
  };
}

function fakeClients(windows: { url: string; visibilityState: string }[] = []) {
  return { matchAll: vi.fn(async () => windows) };
}

function lastShown(registration: ReturnType<typeof fakeRegistration>) {
  const call = registration.showNotification.mock.calls.at(-1) as unknown as [
    string,
    Record<string, unknown>,
  ];
  return { title: call[0], options: call[1] };
}

describe('sw.js parsePushPayload', () => {
  it('returns the parsed JSON body', () => {
    const payload = messagePayload();
    expect(sw.parsePushPayload({ json: () => payload })).toEqual(payload);
  });

  it('falls back to the raw text body when the JSON is malformed', () => {
    const event = {
      json: () => {
        throw new SyntaxError('Unexpected token');
      },
      text: () => 'not json at all',
    };
    expect(sw.parsePushPayload(event)).toEqual({
      title: 'Sorento',
      body: 'not json at all',
    });
  });

  it('returns an empty payload when the push carries no data', () => {
    expect(sw.parsePushPayload(null)).toEqual({});
  });
});

describe('sw.js handlePushPayload - coalescing (AC-M21)', () => {
  let registration: ReturnType<typeof fakeRegistration>;

  beforeEach(() => {
    registration = fakeRegistration();
  });

  it('shows the message text and a count of 1 when nothing is displayed for the tag', async () => {
    const result = await sw.handlePushPayload(messagePayload(), {
      registration,
      clients: fakeClients(),
    });

    expect(result.shown).toBe(true);
    expect(registration.getNotifications).toHaveBeenCalledWith({ tag: TAG });
    const { title, options } = lastShown(registration);
    expect(title).toBe('Ah Meng (Sorento Kitchen)');
    expect(options.body).toBe('Can I get the price for the 900mm hood?');
    expect(options.tag).toBe(TAG);
    expect(options.renotify).toBe(true);
    expect((options.data as Record<string, unknown>).messageCount).toBe(1);
    expect((options.data as Record<string, unknown>).tag).toBe(TAG);
  });

  it('replaces the displayed notification in place and reads "<N> new messages"', async () => {
    registration = fakeRegistration([
      { tag: TAG, data: { messageCount: 1, tag: TAG } },
    ]);

    const result = await sw.handlePushPayload(messagePayload(), {
      registration,
      clients: fakeClients(),
    });

    expect(result.shown).toBe(true);
    expect(registration.showNotification).toHaveBeenCalledTimes(1);
    const { title, options } = lastShown(registration);
    expect(title).toBe('Ah Meng (Sorento Kitchen)');
    expect(options.body).toBe('2 new messages');
    expect(options.tag).toBe(TAG);
    expect(options.renotify).toBe(true);
    expect((options.data as Record<string, unknown>).messageCount).toBe(2);
  });

  it('keeps counting across further pushes', async () => {
    registration = fakeRegistration([
      { tag: TAG, data: { messageCount: 5, tag: TAG } },
    ]);

    await sw.handlePushPayload(messagePayload(), {
      registration,
      clients: fakeClients(),
    });

    expect(lastShown(registration).options.body).toBe('6 new messages');
  });

  it('treats a displayed notification with no stored count as one message', async () => {
    registration = fakeRegistration([{ tag: TAG, data: {} }]);

    await sw.handlePushPayload(messagePayload(), {
      registration,
      clients: fakeClients(),
    });

    expect(lastShown(registration).options.body).toBe('2 new messages');
  });
});

describe('sw.js handlePushPayload - visible-thread suppression (AC-M22, AC-M23)', () => {
  it('shows nothing when a visible window is on that tracking page', async () => {
    const registration = fakeRegistration();
    const clients = fakeClients([
      {
        url: `http://localhost:3000/sla-management/conversations?contact=${CONTACT_ID}`,
        visibilityState: 'visible',
      },
    ]);

    const result = await sw.handlePushPayload(messagePayload(), {
      registration,
      clients,
    });

    expect(result).toEqual({ shown: false, reason: 'thread-visible' });
    expect(registration.showNotification).not.toHaveBeenCalled();
    expect(clients.matchAll).toHaveBeenCalledWith({
      type: 'window',
      includeUncontrolled: true,
    });
  });

  it('shows nothing when a visible window is on the contact-filtered list', async () => {
    const registration = fakeRegistration();
    const link = `/sla-management/conversations?contact=${CONTACT_ID}`;
    const clients = fakeClients([
      {
        url: `http://localhost:3000/sla-management/conversations?contact=${CONTACT_ID}`,
        visibilityState: 'visible',
      },
    ]);

    const result = await sw.handlePushPayload(messagePayload(link), {
      registration,
      clients,
    });

    expect(result.shown).toBe(false);
    expect(registration.showNotification).not.toHaveBeenCalled();
  });

  it('shows the notification when the window on that thread is hidden', async () => {
    const registration = fakeRegistration();
    const clients = fakeClients([
      {
        url: `http://localhost:3000/sla-management/conversations?contact=${CONTACT_ID}`,
        visibilityState: 'hidden',
      },
    ]);

    const result = await sw.handlePushPayload(messagePayload(), {
      registration,
      clients,
    });

    expect(result.shown).toBe(true);
    expect(registration.showNotification).toHaveBeenCalledTimes(1);
  });

  it('shows the notification when the visible window is on a different thread', async () => {
    const registration = fakeRegistration();
    const clients = fakeClients([
      {
        url: 'http://localhost:3000/sla-management/conversations?contact=some-other-id',
        visibilityState: 'visible',
      },
      { url: 'http://localhost:3000/dashboard', visibilityState: 'visible' },
    ]);

    const result = await sw.handlePushPayload(messagePayload(), {
      registration,
      clients,
    });

    expect(result.shown).toBe(true);
  });

  it('shows the notification when no window is open at all', async () => {
    const registration = fakeRegistration();

    const result = await sw.handlePushPayload(messagePayload(), {
      registration,
      clients: fakeClients([]),
    });

    expect(result.shown).toBe(true);
  });

  it('does not suppress a bare list link, which names no thread', async () => {
    const registration = fakeRegistration();
    const clients = fakeClients([
      {
        url: 'http://localhost:3000/sla-management/conversations',
        visibilityState: 'visible',
      },
    ]);

    const result = await sw.handlePushPayload(
      messagePayload('/sla-management/conversations'),
      { registration, clients },
    );

    expect(result.shown).toBe(true);
  });
});

describe('sw.js handlePushPayload - non-message pushes are untouched', () => {
  it('shows a payload with no tag exactly as before, with no coalescing or suppression', async () => {
    const registration = fakeRegistration();
    const clients = fakeClients([
      { url: 'http://localhost:3000/anything', visibilityState: 'visible' },
    ]);

    const result = await sw.handlePushPayload(
      {
        title: 'SLA escalated',
        body: 'Ticket SLA-1042 breached tier 1',
        data: { link: '/sla-management/conversations?contact=abc' },
      },
      { registration, clients },
    );

    expect(result.shown).toBe(true);
    expect(clients.matchAll).not.toHaveBeenCalled();
    expect(registration.getNotifications).not.toHaveBeenCalled();
    const { title, options } = lastShown(registration);
    expect(title).toBe('SLA escalated');
    expect(options.body).toBe('Ticket SLA-1042 breached tier 1');
    expect(options.tag).toBeUndefined();
    expect(options.renotify).toBeUndefined();
    expect(options.data).toEqual({
      link: '/sla-management/conversations?contact=abc',
    });
  });

  it('shows the default title and an empty body for a payload with nothing in it', async () => {
    const registration = fakeRegistration();

    const result = await sw.handlePushPayload(
      {},
      { registration, clients: fakeClients() },
    );

    expect(result.shown).toBe(true);
    const { title, options } = lastShown(registration);
    expect(title).toBe('Sorento');
    expect(options.body).toBe('');
    expect(options.data).toEqual({});
  });
});

describe('sw.js push listener wiring', () => {
  it('parses a malformed push and shows the text fallback', async () => {
    const registration = fakeRegistration();
    const clients = fakeClients();
    // The listener reads these off `self` at event time.
    (globalThis as unknown as Record<string, unknown>).registration =
      registration;
    (globalThis as unknown as Record<string, unknown>).clients = clients;

    const pending: Promise<unknown>[] = [];
    const event = Object.assign(new Event('push'), {
      data: {
        json: () => {
          throw new SyntaxError('Unexpected token');
        },
        text: () => 'plain text push',
      },
      waitUntil: (p: Promise<unknown>) => pending.push(p),
    });

    self.dispatchEvent(event as Event);
    await Promise.all(pending);

    expect(registration.showNotification).toHaveBeenCalledTimes(1);
    const { title, options } = lastShown(registration);
    expect(title).toBe('Sorento');
    expect(options.body).toBe('plain text push');
  });
});
