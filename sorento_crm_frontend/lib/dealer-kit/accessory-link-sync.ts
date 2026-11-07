/**
 * PRICETAG-ACCESSORY-DESIGNER: the live link between linked accessories boxes and their saved template,
 * worked out after a tag template saves. Nothing here touches React: the page hands in how to read and
 * write a template.
 *
 * Rules (the root of "never push an old design over a newer one"):
 *  - a box with no baseline follows the server and is never pushed;
 *  - a box changed since its baseline is pushed ONLY when the server still holds the version the
 *    baseline was taken from (`base_updated_at`), else the server wins for EVERY box of that template;
 *  - a push the server refuses as stale is not retried: the latest design is followed instead.
 */
import {
  changedLinkedDesign,
  designKey,
  linkedBoxDesigns,
  linkedPresetIds,
  type AccessoryDesign,
  type LinkAction,
} from './accessory-card';

type Layers = readonly { id: string; props: { kind: string } }[] | null | undefined;

export interface LinkBaseline {
  /** `designKey` of the design the boxes had when the baseline was taken. */
  key: string;
  /** The template's `updated_at` (as sent by the API) at that moment; null = unknown. */
  updatedAt: string | null;
}

export interface LinkTemplate {
  design: AccessoryDesign;
  updated_at: string;
}

export interface LinkSyncDeps {
  /** The template as the server holds it now; null when it no longer exists. */
  fetch: (id: string) => Promise<LinkTemplate | null>;
  /** Write `design` based on `baseUpdatedAt`; rejects with a stale error when the server moved on. */
  push: (id: string, design: AccessoryDesign, baseUpdatedAt: string) => Promise<LinkTemplate>;
  isStale: (error: unknown) => boolean;
}

export type LinkMessage = 'deleted' | 'elsewhere' | { error: string };

export interface LinkSyncResult {
  actions: LinkAction[];
  messages: LinkMessage[];
  /** Linked boxes were added, removed or pushed: usage counts changed. */
  usageChanged: boolean;
}

/** The baseline a freshly loaded tag template starts from: its boxes as saved, the template's version now. */
export async function captureBaselines(
  layers: Layers,
  fetch: LinkSyncDeps['fetch'],
): Promise<Map<string, LinkBaseline>> {
  const out = new Map<string, LinkBaseline>();
  for (const [id, linked] of linkedBoxDesigns(layers)) {
    try {
      const record = await fetch(id);
      if (record) out.set(id, { key: linked.key, updatedAt: record.updated_at });
    } catch {
      // No baseline: the first sync follows the server.
    }
  }
  return out;
}

export async function syncLinkedBoxes(
  layers: Layers,
  baselines: Map<string, LinkBaseline>,
  deps: LinkSyncDeps,
): Promise<LinkSyncResult> {
  const ids = linkedPresetIds(layers);
  const actions: LinkAction[] = [];
  const messages: LinkMessage[] = [];
  let usageChanged = ids.length !== baselines.size || ids.some((id) => !baselines.has(id));
  for (const id of [...baselines.keys()]) if (!ids.includes(id)) baselines.delete(id);

  const follow = (id: string, record: LinkTemplate) => {
    actions.push({ kind: 'set', id, design: record.design });
    baselines.set(id, { key: designKey(record.design), updatedAt: record.updated_at });
  };

  for (const id of ids) {
    let server: LinkTemplate | null;
    try {
      server = await deps.fetch(id);
    } catch (error) {
      messages.push({ error: error instanceof Error ? error.message : 'Could not check the accessories template' });
      continue;
    }
    if (!server) {
      actions.push({ kind: 'detach', id });
      baselines.delete(id);
      messages.push('deleted');
      usageChanged = true;
      continue;
    }
    const serverKey = designKey(server.design);
    const base = baselines.get(id);
    if (!base) {
      follow(id, server);
      continue;
    }
    const changed = changedLinkedDesign(layers, id, base.key);
    if (!changed) {
      if (serverKey !== base.key) follow(id, server);
      else baselines.set(id, { key: base.key, updatedAt: server.updated_at });
      continue;
    }
    const key = designKey(changed);
    if (base.updatedAt === null || server.updated_at !== base.updatedAt) {
      // Somebody saved since this tag's design was based on it: the server wins, for every box.
      follow(id, server);
      messages.push('elsewhere');
      continue;
    }
    if (key === serverKey) {
      baselines.set(id, { key, updatedAt: server.updated_at });
      continue;
    }
    try {
      const saved = await deps.push(id, changed, base.updatedAt);
      baselines.set(id, { key, updatedAt: saved.updated_at });
      usageChanged = true;
      const othersDiffer = (layers ?? []).some((layer) => {
        const own = linkedBoxDesigns([layer]).get(id);
        return own !== undefined && own.key !== key;
      });
      if (othersDiffer) actions.push({ kind: 'set', id, design: changed });
    } catch (error) {
      if (!deps.isStale(error)) {
        messages.push({ error: error instanceof Error ? error.message : 'Could not update the accessories template' });
        continue;
      }
      // Lost the race: take the latest design, do not retry.
      try {
        const latest = await deps.fetch(id);
        if (latest) follow(id, latest);
        else {
          actions.push({ kind: 'detach', id });
          baselines.delete(id);
        }
        messages.push('elsewhere');
      } catch (inner) {
        messages.push({ error: inner instanceof Error ? inner.message : 'Could not check the accessories template' });
      }
    }
  }
  return { actions, messages, usageChanged };
}
