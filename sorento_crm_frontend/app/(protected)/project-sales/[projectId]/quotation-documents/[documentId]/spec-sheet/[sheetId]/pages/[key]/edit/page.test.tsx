import { describe, expect, it, vi } from 'vitest';

vi.mock('@/app/components/common/RequireAccess', () => ({
  default: ({ children }: { children: unknown }) => children,
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: unknown }) => children,
}));
vi.mock('../../../components/SpecSheetPageEditor', () => ({
  SpecSheetPageEditor: () => null,
}));

import EditProjectQuotationSpecSheetPage from './page';
import { SpecSheetPageEditor } from '../../../components/SpecSheetPageEditor';

/** Find the editor element in the returned tree and read the page key it is given. */
function pageKeyOf(node: unknown): string | undefined {
  if (!node || typeof node !== 'object') return undefined;
  const el = node as { type?: unknown; props?: { pageKey?: string; children?: unknown } };
  if (el.type === SpecSheetPageEditor) return el.props?.pageKey;
  const kids = el.props?.children;
  for (const child of Array.isArray(kids) ? kids : [kids]) {
    const found = pageKeyOf(child);
    if (found !== undefined) return found;
  }
  return undefined;
}

describe('Edit spec sheet page route', () => {
  // The reader links with encodeURIComponent(page.key), and the App Router hands a server
  // page its dynamic segment still encoded, so the route decodes it exactly once. Without that
  // the service encodes again and asks the API for `set%253A...`, which 404s.
  it.each([
    ['set:5f96ff63-e124-4518-a41f-777f15963ceb'],
    ['code:AB/12,X'],
    ['cover'],
  ])('passes the decoded key %s to the editor', async (key) => {
    const tree = await EditProjectQuotationSpecSheetPage({
      params: Promise.resolve({ projectId: 'p', documentId: 'd', sheetId: 's', key: encodeURIComponent(key) }),
    });
    expect(pageKeyOf(tree)).toBe(key);
  });
});
