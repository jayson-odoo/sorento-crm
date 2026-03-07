import type { MenuConfig, MenuItem } from '@/config/types';

export interface FlattenedMenuItem {
  path: string;
  title: string;
}

/**
 * Recursively flatten menu config to leaf items with path and title.
 * Skips headings and disabled items.
 */
export function flattenMenuItems(items: MenuConfig): FlattenedMenuItem[] {
  const result: FlattenedMenuItem[] = [];
  function walk(nodes: MenuConfig) {
    for (const item of nodes) {
      if (item.heading || item.disabled) continue;
      if (item.path && item.title) {
        result.push({ path: item.path, title: item.title });
      }
      if (item.children?.length) {
        walk(item.children);
      }
    }
  }
  walk(items);
  return result;
}

/**
 * Resolve display title for a path: first try exact path match, then prefix match (path + ? or path as prefix).
 * For paths with query (e.g. attachment-directories?directoryId=xyz), use label if provided.
 */
export function getTitleForPath(
  flattened: FlattenedMenuItem[],
  path: string,
  label?: string | null
): string {
  if (label?.trim()) return label.trim();
  const basePath = path.split('?')[0];
  const exact = flattened.find((m) => m.path === path || m.path === basePath);
  if (exact) return exact.title;
  const prefix = flattened.find(
    (m) => path.startsWith(m.path) || basePath.startsWith(m.path)
  );
  if (prefix) return prefix.title;
  return 'Unknown';
}
