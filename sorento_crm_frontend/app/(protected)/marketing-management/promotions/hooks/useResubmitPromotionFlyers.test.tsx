/**
 * Tests for useResubmitPromotionFlyers - the Resubmit bulk-action mutation.
 *
 * The two properties that matter operationally: the resubmits are SEQUENTIAL (each
 * one starts a Gemini extraction on the n8n side, so a page of selections must not
 * fire at once), and one failure must not abort the remaining flyers.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock('@/app/(protected)/resource-management/attachments/services/attachmentService', () => ({
  resubmitAttachmentWebhook: vi.fn(),
}));
vi.mock('../services/promotionService', () => ({
  getPromotions: vi.fn(),
  getPromotion: vi.fn(),
  createPromotion: vi.fn(),
  updatePromotion: vi.fn(),
  deletePromotion: vi.fn(),
  bulkDeletePromotions: vi.fn(),
  bulkUpdateAccessLevels: vi.fn(),
  getPromotionProducts: vi.fn(),
  addPromotionProduct: vi.fn(),
  removePromotionProduct: vi.fn(),
  updatePromotionProductPrice: vi.fn(),
  createPromotionGroup: vi.fn(),
  updatePromotionGroup: vi.fn(),
  deletePromotionGroup: vi.fn(),
  compilePromotionsPdf: vi.fn(),
  PROMOTION_NEIGHBOURS_PATH: '/promotions/neighbours',
}));

import { toast } from 'sonner';
import { resubmitAttachmentWebhook } from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import { useResubmitPromotionFlyers } from './usePromotions';

const mockResubmit = resubmitAttachmentWebhook as unknown as ReturnType<typeof vi.fn>;

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe('useResubmitPromotionFlyers', () => {
  beforeEach(() => vi.clearAllMocks());

  it('resubmits one attachment at a time rather than all at once', async () => {
    let inFlight = 0;
    let maxInFlight = 0;
    mockResubmit.mockImplementation(async () => {
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await Promise.resolve();
      inFlight -= 1;
      return { message: 'ok', integration_log_id: 'log-1' };
    });
    const client = new QueryClient();

    const { result } = renderHook(() => useResubmitPromotionFlyers(), {
      wrapper: wrapper(client),
    });
    result.current.mutate(['a-1', 'a-2', 'a-3']);

    await waitFor(() => expect(mockResubmit).toHaveBeenCalledTimes(3));
    expect(maxInFlight).toBe(1);
    expect(mockResubmit.mock.calls.map((c) => c[0])).toEqual(['a-1', 'a-2', 'a-3']);
  });

  it('invalidates the promotions list and toasts the success count', async () => {
    mockResubmit.mockResolvedValue({ message: 'ok', integration_log_id: 'log-1' });
    const client = new QueryClient();
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useResubmitPromotionFlyers(), {
      wrapper: wrapper(client),
    });
    result.current.mutate(['a-1', 'a-2']);

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['promotions'] }),
    );
    expect(toast.success).toHaveBeenCalledWith(
      '2 flyer(s) sent for re-extraction. Products update once n8n finishes.',
    );
  });

  it('keeps going after a failure and reports both tallies', async () => {
    mockResubmit
      .mockRejectedValueOnce(new Error('Webhook URL not configured'))
      .mockResolvedValueOnce({ message: 'ok', integration_log_id: 'log-2' })
      .mockResolvedValueOnce({ message: 'ok', integration_log_id: 'log-3' });
    const client = new QueryClient();

    const { result } = renderHook(() => useResubmitPromotionFlyers(), {
      wrapper: wrapper(client),
    });
    result.current.mutate(['a-1', 'a-2', 'a-3']);

    // The failure of a-1 must not stop a-2 and a-3.
    await waitFor(() => expect(mockResubmit).toHaveBeenCalledTimes(3));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        '2 flyer(s) sent for re-extraction. Products update once n8n finishes.',
      ),
    );
    expect(toast.error).toHaveBeenCalledWith(
      '1 flyer(s) could not be resubmitted: Webhook URL not configured',
    );
  });

  it('does not claim success when every flyer failed', async () => {
    mockResubmit.mockRejectedValue(new Error('n8n unreachable'));
    const client = new QueryClient();

    const { result } = renderHook(() => useResubmitPromotionFlyers(), {
      wrapper: wrapper(client),
    });
    result.current.mutate(['a-1', 'a-2']);

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.success).not.toHaveBeenCalled();
  });
});
