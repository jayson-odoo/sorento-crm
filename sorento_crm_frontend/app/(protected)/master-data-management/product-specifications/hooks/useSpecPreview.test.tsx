/**
 * S4: a preview run that fails - most commonly "one is already running" (409
 * `spec_preview_running`) - surfaces as a toast, not only the inline `Alert` a
 * status of `error` renders. `status` flips to `error` regardless, so the button
 * (`SpecPreviewPanel`, disabled only while `pending`) is enabled again the instant
 * the toast fires - a silent refusal there would read as "nothing happened".
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock('../services/productSpecService', () => ({
  previewSpecRules: vi.fn(),
  getSpecPreview: vi.fn(),
}));

import { toast } from 'sonner';
import {
  previewSpecRules,
  getSpecPreview,
} from '../services/productSpecService';
import { useSpecPreview } from './useSpecPreview';

const mockStart = previewSpecRules as unknown as ReturnType<typeof vi.fn>;
const mockPoll = getSpecPreview as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => vi.clearAllMocks());

describe('useSpecPreview - run failure', () => {
  it('toasts the extracted error and lands on status "error"', async () => {
    mockStart.mockRejectedValue(
      new Error('A preview is already running. Wait for it to finish.'),
    );

    const { result } = renderHook(() => useSpecPreview('dim_length'));
    act(() => {
      result.current.run([]);
    });

    await waitFor(() => expect(result.current.status).toBe('error'));

    expect(result.current.error).toBe(
      'A preview is already running. Wait for it to finish.',
    );
    expect(toast.error).toHaveBeenCalledWith(
      'A preview is already running. Wait for it to finish.',
    );
  });

  it('does not toast while the job is merely pending', async () => {
    mockStart.mockResolvedValue({ jobId: 'job-1' });
    mockPoll.mockResolvedValue({ status: 'pending' });

    const { result } = renderHook(() => useSpecPreview('dim_length'));
    act(() => {
      result.current.run([]);
    });

    await waitFor(() => expect(result.current.status).toBe('pending'));
    expect(toast.error).not.toHaveBeenCalled();
  });
});
