/**
 * Tests for the TCK-2026-000020 upload-conflict UX hook.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

import { useUploadConflict } from './use-upload-conflict';
import {
  AttachmentFilenameCollisionError,
  type AttachmentFilenameCollision,
} from '@/app/(protected)/resource-management/attachments/services/attachmentService';

type PerformResult = { id: string; onConflict?: 'copy' | 'replace' };
type PerformFn = (onConflict?: 'copy' | 'replace') => Promise<PerformResult>;

const COLLISION: AttachmentFilenameCollision = {
  existing_attachment_id: 'att-1',
  existing_file_name: 'duplicate.pdf',
  existing_target_entity_type: 'product',
  existing_target_field_keys: ['spec'],
};

type HarnessHandle = {
  trigger: (perform: PerformFn) => Promise<PerformResult | null>;
};

function Harness({ refObj }: { refObj: { current: HarnessHandle | null } }) {
  const { runUpload, ConflictDialog } = useUploadConflict();
  refObj.current = { trigger: (perform) => runUpload(perform) };
  return <div data-testid="harness">{ConflictDialog}</div>;
}

function mountHarness() {
  const refObj: { current: HarnessHandle | null } = { current: null };
  render(<Harness refObj={refObj} />);
  if (!refObj.current) throw new Error('Harness ref not assigned');
  return { handle: refObj.current };
}

describe('useUploadConflict', () => {
  it('runUpload resolves with perform result when no collision', async () => {
    const { handle } = mountHarness();
    const perform: PerformFn = vi.fn(async (onConflict) => ({ id: 'ok', onConflict }));

    const result = await handle.trigger(perform);

    expect(result).toEqual({ id: 'ok', onConflict: undefined });
    expect(perform).toHaveBeenCalledTimes(1);
  });

  it('opens conflict dialog and re-runs with copy choice', async () => {
    const { handle } = mountHarness();
    const perform: PerformFn = vi
      .fn()
      .mockImplementationOnce(async () => {
        throw new AttachmentFilenameCollisionError(COLLISION);
      })
      .mockImplementationOnce(async (onConflict) => ({ id: 'after-copy', onConflict }));

    const triggerPromise = handle.trigger(perform);

    await waitFor(() => screen.getByText(/File already exists in this folder/i));
    expect(screen.getByText('duplicate.pdf')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Create copy/i }));
    const resolved = await triggerPromise;

    expect(perform).toHaveBeenCalledTimes(2);
    expect(perform).toHaveBeenNthCalledWith(2, 'copy');
    expect(resolved).toEqual({ id: 'after-copy', onConflict: 'copy' });
  });

  it('re-runs with replace choice', async () => {
    const { handle } = mountHarness();
    const perform: PerformFn = vi
      .fn()
      .mockImplementationOnce(async () => {
        throw new AttachmentFilenameCollisionError(COLLISION);
      })
      .mockImplementationOnce(async (onConflict) => ({ id: 'after-replace', onConflict }));

    const triggerPromise = handle.trigger(perform);

    await waitFor(() => screen.getByText(/File already exists in this folder/i));
    fireEvent.click(screen.getByRole('button', { name: /Replace existing/i }));
    const resolved = await triggerPromise;

    expect(perform).toHaveBeenCalledTimes(2);
    expect(perform).toHaveBeenNthCalledWith(2, 'replace');
    expect(resolved).toEqual({ id: 'after-replace', onConflict: 'replace' });
  });

  it('returns null when user cancels and does not retry perform', async () => {
    const { handle } = mountHarness();
    const perform: PerformFn = vi.fn(async () => {
      throw new AttachmentFilenameCollisionError(COLLISION);
    });

    const triggerPromise = handle.trigger(perform);

    await waitFor(() => screen.getByText(/File already exists in this folder/i));
    fireEvent.click(screen.getByRole('button', { name: /Cancel/i }));
    const resolved = await triggerPromise;

    expect(perform).toHaveBeenCalledTimes(1);
    expect(resolved).toBeNull();
  });
});
