import type { AttachmentDirectoryTreeNode } from '../../attachments/services/directoryService';

export interface BreadcrumbCrumb {
  /** null = drive root. */
  id: string | null;
  name: string;
}

/**
 * Build the breadcrumb trail (root → … → folder) for `folderId` from the tree.
 * Always begins with the synthetic root crumb. Returns just the root when
 * `folderId` is null or not found.
 */
export function buildBreadcrumb(
  tree: AttachmentDirectoryTreeNode[],
  folderId: string | null,
  rootLabel = 'All files'
): BreadcrumbCrumb[] {
  const root: BreadcrumbCrumb = { id: null, name: rootLabel };
  if (!folderId) return [root];

  const trail: BreadcrumbCrumb[] = [];
  const walk = (nodes: AttachmentDirectoryTreeNode[], path: BreadcrumbCrumb[]): boolean => {
    for (const node of nodes) {
      const next = [...path, { id: node.id, name: node.name }];
      if (node.id === folderId) {
        trail.push(...next);
        return true;
      }
      if (node.children?.length && walk(node.children, next)) return true;
    }
    return false;
  };
  walk(tree, []);
  return [root, ...trail];
}
