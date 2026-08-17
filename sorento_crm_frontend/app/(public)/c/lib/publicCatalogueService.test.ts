/**
 * The public catalogue reader.
 *
 * The interesting behaviour is not the happy path, it is that the page commits
 * twice on a cold open and the reader must still download the brochure once.
 * Measured on the seeded A3 flyer: two fetches eleven milliseconds apart from a
 * single navigation, 433KB each.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  CatalogueNotFoundError,
  readPublishedCatalogue,
} from './publicCatalogueService';

const PAYLOAD = { name: 'Flyer', slug: 'flyer', doc: { sections: [] } };

function respondWith(status: number, body: unknown = PAYLOAD) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

/** A fetch that does not settle until the test says so. */
function deferredFetch() {
  let release: (value: Response) => void = () => {};
  const pending = new Promise<Response>((resolve) => {
    release = resolve;
  });
  const spy = vi.fn(() => pending);
  return { spy, release: () => release(respondWith(200)) };
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => respondWith(200)));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('readPublishedCatalogue', () => {
  it('reads the company-scoped public route', async () => {
    await readPublishedCatalogue('SRT', 'a3-flyer');

    const [url, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain('/api/v1/public/c/SRT/a3-flyer');
    // `no-store` opted out of the ETag the server sends, so a reader who
    // reopened the link paid for the whole document again.
    expect(init?.cache).toBeUndefined();
  });

  it('does not fetch twice when the page commits twice', async () => {
    const { spy, release } = deferredFetch();
    vi.stubGlobal('fetch', spy);

    const first = readPublishedCatalogue('SRT', 'a3-flyer');
    const second = readPublishedCatalogue('SRT', 'a3-flyer');
    release();

    await expect(first).resolves.toEqual(PAYLOAD);
    await expect(second).resolves.toEqual(PAYLOAD);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('does not confuse two catalogues that are read at the same moment', async () => {
    const { spy, release } = deferredFetch();
    vi.stubGlobal('fetch', spy);

    void readPublishedCatalogue('SRT', 'a3-flyer');
    void readPublishedCatalogue('MCH', 'a3-flyer');
    release();

    // Same slug, different company: these are different documents and the
    // company segment in the address is the whole reason the route exists.
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('lets a later read retry after a failed one', async () => {
    const spy = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(respondWith(200));
    vi.stubGlobal('fetch', spy);

    await expect(readPublishedCatalogue('SRT', 'a3-flyer')).rejects.toThrow();
    await expect(readPublishedCatalogue('SRT', 'a3-flyer')).resolves.toEqual(PAYLOAD);
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('reports a missing catalogue as its own error, not a generic failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respondWith(404, {})));

    await expect(readPublishedCatalogue('SRT', 'gone')).rejects.toBeInstanceOf(
      CatalogueNotFoundError,
    );
  });
});
