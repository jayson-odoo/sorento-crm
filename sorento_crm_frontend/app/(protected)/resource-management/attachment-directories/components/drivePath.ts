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

export interface DirectoryOption {
  value: string;
  label: string;
}

/**
 * Every directory in the tree, flattened, each labelled with its full path
 * (`Documents / Packing Lists`) so a folder several levels deep is not confused with a
 * same-named one elsewhere. Feeds a plain `SearchableSelect` - the attachment type's
 * `Default folder` field (R4) and the generic upload dialog's folder picker both need a
 * flat list, not the tree widget `MoveToDialog` uses to move files around.
 */
export function flattenDirectoryOptions(
  tree: AttachmentDirectoryTreeNode[]
): DirectoryOption[] {
  const out: DirectoryOption[] = [];
  const walk = (nodes: AttachmentDirectoryTreeNode[], prefix: string) => {
    for (const node of nodes) {
      const label = prefix ? `${prefix} / ${node.name}` : node.name;
      out.push({ value: node.id, label });
      if (node.children?.length) walk(node.children, label);
    }
  };
  walk(tree, '');
  return out;
}
