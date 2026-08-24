/**
 * buildBreadcrumb - the Drive breadcrumb trail (UAC A2).
 */
import { describe, it, expect } from 'vitest';
import { buildBreadcrumb } from './drivePath';
import type { AttachmentDirectoryTreeNode } from '../../attachments/services/directoryService';

const tree: AttachmentDirectoryTreeNode[] = [
  {
    id: 'mkt',
    name: 'Marketing',
    parent_id: null,
    sort_order: 0,
    created_at: '',
    children: [
      {
        id: 'camp',
        name: 'Campaigns',
        parent_id: 'mkt',
        sort_order: 0,
        created_at: '',
        children: [
          { id: 'q1', name: 'Q1', parent_id: 'camp', sort_order: 0, created_at: '', children: [] },
        ],
      },
    ],
  },
];

describe('buildBreadcrumb', () => {
  it('returns only the root crumb when folderId is null', () => {
    expect(buildBreadcrumb(tree, null)).toEqual([{ id: null, name: 'All files' }]);
  });

  it('builds root -> ... -> current for a nested folder', () => {
    expect(buildBreadcrumb(tree, 'q1')).toEqual([
      { id: null, name: 'All files' },
      { id: 'mkt', name: 'Marketing' },
      { id: 'camp', name: 'Campaigns' },
      { id: 'q1', name: 'Q1' },
    ]);
  });

  it('honours a custom root label', () => {
    expect(buildBreadcrumb(tree, 'mkt', 'Home')[0]).toEqual({ id: null, name: 'Home' });
  });

  it('falls back to just root when the folder is not in the tree', () => {
    expect(buildBreadcrumb(tree, 'missing')).toEqual([{ id: null, name: 'All files' }]);
  });
});
