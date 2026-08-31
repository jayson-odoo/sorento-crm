/**
 * buildDriveBulkActions - the single "Action" dropdown gating (UAC F2/F3/F6).
 */
import { describe, it, expect, vi } from 'vitest';
import { buildDriveBulkActions, type DriveBulkActionHandlers } from './driveBulkActions';

const handlers: DriveBulkActionHandlers = {
  onMove: vi.fn(),
  onExport: vi.fn(),
  onSetAccessLevels: vi.fn(),
  onSetAttachmentType: vi.fn(),
  onSetCompany: vi.fn(),
  onResubmit: vi.fn(),
  onDelete: vi.fn(),
  onRestore: vi.fn(),
};

function keys(state: Parameters<typeof buildDriveBulkActions>[0]) {
  return buildDriveBulkActions(state, handlers).map((a) => a.key);
}

describe('buildDriveBulkActions', () => {
  it('returns nothing with an empty selection', () => {
    expect(
      keys({
        selectionCount: 0,
        selectionHasFolder: false,
        isTrashView: false,
        isResubmitting: false,
        canRestore: false,
      })
    ).toEqual([]);
  });

  it('F2: a file-only selection exposes ALL bulk actions in one menu', () => {
    expect(
      keys({
        selectionCount: 2,
        selectionHasFolder: false,
        isTrashView: false,
        isResubmitting: false,
        canRestore: false,
      })
    ).toEqual([
      'bulk-move',
      'bulk-export',
      'bulk-access-levels',
      'bulk-attachment-type',
      'bulk-company',
      'bulk-resubmit',
      'bulk-delete',
    ]);
  });

  it('F3: when the selection contains a folder, file-only actions are disabled but shared ones stay enabled', () => {
    const actions = buildDriveBulkActions(
      {
        selectionCount: 2,
        selectionHasFolder: true,
        isTrashView: false,
        isResubmitting: false,
        canRestore: false,
      },
      handlers
    );
    const byKey = Object.fromEntries(actions.map((a) => [a.key, a]));
    // shared
    expect(byKey['bulk-move'].disabled).toBeFalsy();
    expect(byKey['bulk-delete'].disabled).toBeFalsy();
    // file-only -> disabled with a reason
    expect(byKey['bulk-export'].disabled).toBe(true);
    expect(byKey['bulk-access-levels'].disabled).toBe(true);
    expect(byKey['bulk-attachment-type'].disabled).toBe(true);
    expect(byKey['bulk-resubmit'].disabled).toBe(true);
    expect(byKey['bulk-export'].disabledReason).toMatch(/folder/i);
    expect(byKey['bulk-access-levels'].disabledReason).toMatch(/folder/i);
  });

  it('F6: Rename and Replace are never in the bulk menu', () => {
    const all = keys({
      selectionCount: 3,
      selectionHasFolder: false,
      isTrashView: false,
      isResubmitting: false,
      canRestore: false,
    });
    expect(all).not.toContain('bulk-rename');
    expect(all).not.toContain('bulk-replace');
  });

  it('does NOT include a Download-as-ZIP action (feature dropped)', () => {
    const all = keys({
      selectionCount: 2,
      selectionHasFolder: false,
      isTrashView: false,
      isResubmitting: false,
      canRestore: false,
    });
    expect(all).not.toContain('bulk-zip');
  });

  it('Trash exposes only Restore + Delete', () => {
    expect(
      keys({
        selectionCount: 1,
        selectionHasFolder: false,
        isTrashView: true,
        isResubmitting: false,
        canRestore: true,
      })
    ).toEqual(['bulk-restore', 'bulk-permanent-delete']);
  });
});
