/**
 * The two save contracts the shell hands the designer (B2/B3, D22).
 *
 * They used to be one handler, and the autosave inherited the manual button's
 * manners: a "Tag sheet saved" toast roughly once a second while somebody
 * designed, and - worse - a swallowed failure, so the header read "Saved" over
 * work that had never left the browser. They are now two:
 *
 *  * `onAutosave` writes the DRAFT, says nothing, and RETHROWS so
 *    `useAutosave` can turn the failure into "Save failed (Retry)";
 *  * `onSave` writes an immutable version, toasts either way, and rethrows so
 *    a caller that saves as a precondition can abort.
 *
 * The designer itself is Konva-backed, so it is replaced by a stand-in that
 * exposes the two props as buttons - what is under test is the shell's
 * wiring, not the canvas.
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { toast } from '@/lib/toast';
const mockToastSuccess = vi.mocked(toast.success);
const mockToastError = vi.mocked(toast.error);

vi.mock('../../../../services/priceTagRequestService', () => ({
  getPriceTagRequest: vi.fn(),
  getTagSheetDoc: vi.fn(),
  saveTagSheetDoc: vi.fn(),
  saveTagSheetDraft: vi.fn(),
}));

// The last props the designer was rendered with - the test drives the two
// handlers directly, which is the whole contract this file is about.
type SaveFn = (doc: unknown) => Promise<void>;
type AutosaveFn = (doc: unknown, options?: { keepalive?: boolean }) => Promise<void>;
let lastProps: { onSave: SaveFn; onAutosave: AutosaveFn } | null = null;

vi.mock('./RequestTagDesigner', () => ({
  RequestTagDesigner: (props: { onSave: SaveFn; onAutosave: AutosaveFn }) => {
    lastProps = props;
    return <div data-testid="designer">designer</div>;
  },
}));

import {
  getPriceTagRequest,
  getTagSheetDoc,
  saveTagSheetDoc,
  saveTagSheetDraft,
} from '../../../../services/priceTagRequestService';
import RequestTagDesignerShell from './RequestTagDesignerShell';

const mockGetRequest = vi.mocked(getPriceTagRequest);
const mockGetDoc = vi.mocked(getTagSheetDoc);
const mockSaveDoc = vi.mocked(saveTagSheetDoc);
const mockSaveDraft = vi.mocked(saveTagSheetDraft);

const DOC = { kind: 'tag_sheet', sheets: [] } as never;

beforeEach(() => {
  vi.clearAllMocks();
  lastProps = null;
  mockGetRequest.mockResolvedValue({ id: 'req-1', doc_number: 'PT-000001' } as never);
  mockGetDoc.mockResolvedValue(null);
});

async function mountShell() {
  render(<RequestTagDesignerShell requestId="req-1" />);
  await waitFor(() => expect(screen.getByTestId('designer')).toBeInTheDocument());
  return lastProps!;
}

describe('RequestTagDesignerShell - the autosave contract (B2, D22)', () => {
  it('writes the DRAFT route and says nothing on success', async () => {
    const { onAutosave } = await mountShell();
    mockSaveDraft.mockResolvedValue(undefined);

    await onAutosave(DOC);

    expect(mockSaveDraft).toHaveBeenCalledWith('req-1', DOC, {});
    // No version is written by an autosave - that is the whole point of B1.
    expect(mockSaveDoc).not.toHaveBeenCalled();
    // And no toast: the header's indicator is the entire report (D22).
    expect(mockToastSuccess).not.toHaveBeenCalled();
    expect(mockToastError).not.toHaveBeenCalled();
  });

  it('rethrows a failure instead of swallowing it into a success', async () => {
    const { onAutosave } = await mountShell();
    mockSaveDraft.mockRejectedValue(new Error('network down'));

    await expect(onAutosave(DOC)).rejects.toThrow('network down');
    // Still silent - `useAutosave` turns this into "Save failed (Retry)".
    expect(mockToastError).not.toHaveBeenCalled();
  });

  it('passes keepalive through for the page-teardown flush', async () => {
    const { onAutosave } = await mountShell();
    mockSaveDraft.mockResolvedValue(undefined);

    await onAutosave(DOC, { keepalive: true });

    expect(mockSaveDraft).toHaveBeenCalledWith('req-1', DOC, { keepalive: true });
  });
});

describe('RequestTagDesignerShell - the manual Save contract (B3)', () => {
  it('writes a version and toasts on success', async () => {
    const { onSave } = await mountShell();
    mockSaveDoc.mockResolvedValue(undefined);

    await onSave(DOC);

    expect(mockSaveDoc).toHaveBeenCalledWith('req-1', DOC);
    expect(mockSaveDraft).not.toHaveBeenCalled();
    expect(mockToastSuccess).toHaveBeenCalledWith('Tag sheet saved');
  });

  it('toasts the failure AND rethrows, so a precondition save can abort', async () => {
    const { onSave } = await mountShell();
    mockSaveDoc.mockRejectedValue(new Error('the request is no longer designable'));

    await expect(onSave(DOC)).rejects.toThrow('the request is no longer designable');
    expect(mockToastError).toHaveBeenCalledWith('the request is no longer designable');
    expect(mockToastSuccess).not.toHaveBeenCalled();
  });
});
