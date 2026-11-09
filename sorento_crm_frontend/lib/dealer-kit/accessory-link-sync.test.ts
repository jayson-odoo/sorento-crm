import { describe, expect, it, vi } from 'vitest';
import { accessoryDesign, designKey } from './accessory-card';
import { captureBaselines, syncLinkedBoxes, type LinkBaseline, type LinkSyncDeps } from './accessory-link-sync';
import { defaultAccessoriesProps, type AccessoriesLayerProps } from './tag-template-types';

const box = (id: string, header: string) => ({
  id,
  props: { ...defaultAccessoriesProps(), presetId: 'p1', headerText: header } as AccessoriesLayerProps,
});
const design = (header: string) => accessoryDesign(box('x', header).props);
const keyOf = (header: string) => designKey(design(header));

class Stale extends Error {}
function deps(server: { header: string; at: string } | null, extra: Partial<LinkSyncDeps> = {}) {
  const push = vi.fn(async (_id: string, d: ReturnType<typeof design>) => ({ design: d, updated_at: 'U-pushed' }));
  const fetch = vi.fn(async () => (server ? { design: design(server.header), updated_at: server.at } : null));
  return { push, fetch, deps: { fetch, push, isStale: (e: unknown) => e instanceof Stale, ...extra } as LinkSyncDeps };
}
const baselines = (entries: [string, LinkBaseline][]) => new Map(entries);

describe('syncLinkedBoxes', () => {
  it('pushes a box edited against its baseline when the server still holds that version', async () => {
    const d = deps({ header: 'OLD', at: 'U1' });
    const result = await syncLinkedBoxes([box('a', 'EDITED')], baselines([['p1', { key: keyOf('OLD'), updatedAt: 'U1' }]]), d.deps);
    expect(d.push).toHaveBeenCalledWith('p1', expect.objectContaining({ headerText: 'EDITED' }), 'U1');
    expect(result.actions).toEqual([]);
  });

  it('never pushes a box with no baseline: it follows the server', async () => {
    const d = deps({ header: 'SERVER', at: 'U2' });
    const result = await syncLinkedBoxes([box('a', 'PASTED')], baselines([]), d.deps);
    expect(d.push).not.toHaveBeenCalled();
    expect(result.actions).toEqual([{ kind: 'set', id: 'p1', design: design('SERVER') }]);
  });

  it('an older box next to a newer template is not pushed over it (the server moved on)', async () => {
    // The tag was based on U1 with design OLD; somebody saved NEW (U2); this tag still holds an OLD box edited to OLDER.
    const d = deps({ header: 'NEW', at: 'U2' });
    const store = baselines([['p1', { key: keyOf('OLD'), updatedAt: 'U1' }]]);
    const result = await syncLinkedBoxes([box('a', 'OLDER')], store, d.deps);
    expect(d.push).not.toHaveBeenCalled();
    expect(result.actions).toEqual([{ kind: 'set', id: 'p1', design: design('NEW') }]);
    expect(result.messages).toContain('elsewhere');
    expect(store.get('p1')).toEqual({ key: keyOf('NEW'), updatedAt: 'U2' });
  });

  it('a push the server refuses as stale is not retried: the latest design is followed', async () => {
    const push = vi.fn(async () => {
      throw new Stale('stale');
    });
    const fetch = vi
      .fn()
      .mockResolvedValueOnce({ design: design('OLD'), updated_at: 'U1' })
      .mockResolvedValueOnce({ design: design('RACED'), updated_at: 'U3' });
    const store = baselines([['p1', { key: keyOf('OLD'), updatedAt: 'U1' }]]);
    const result = await syncLinkedBoxes([box('a', 'EDITED')], store, { fetch, push, isStale: (e) => e instanceof Stale });
    expect(push).toHaveBeenCalledTimes(1);
    expect(result.actions).toEqual([{ kind: 'set', id: 'p1', design: design('RACED') }]);
    expect(result.messages).toContain('elsewhere');
    expect(store.get('p1')).toEqual({ key: keyOf('RACED'), updatedAt: 'U3' });
  });

  it('detaches when the template is gone', async () => {
    const d = deps(null);
    const result = await syncLinkedBoxes([box('a', 'X')], baselines([['p1', { key: keyOf('X'), updatedAt: 'U1' }]]), d.deps);
    expect(result.actions).toEqual([{ kind: 'detach', id: 'p1' }]);
    expect(result.messages).toContain('deleted');
  });

  it('an unchanged box follows a newer server design', async () => {
    const d = deps({ header: 'NEW', at: 'U2' });
    const result = await syncLinkedBoxes([box('a', 'OLD')], baselines([['p1', { key: keyOf('OLD'), updatedAt: 'U1' }]]), d.deps);
    expect(result.actions).toEqual([{ kind: 'set', id: 'p1', design: design('NEW') }]);
  });
});

describe('captureBaselines', () => {
  it('takes the boxes as saved and the template version now', async () => {
    const d = deps({ header: 'NEW', at: 'U2' });
    const out = await captureBaselines([box('a', 'OLD')], d.deps.fetch);
    expect(out.get('p1')).toEqual({ key: keyOf('OLD'), updatedAt: 'U2' });
  });
});
