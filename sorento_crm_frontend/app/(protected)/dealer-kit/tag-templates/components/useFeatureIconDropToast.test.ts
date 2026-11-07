/**
 * Crew browser pass (5 Nov): the template designer warns the MOMENT a change makes a feature icon
 * drop (preview product, size, spacing, box resize), once: on the move from none dropped to some,
 * or when more drop than before. No toast for a steady state or an improvement.
 */
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { warning: vi.fn(), success: vi.fn(), error: vi.fn() } }));

import { toast } from '@/lib/toast';
import { useFeatureIconDropToast } from './useFeatureIconDropToast';

beforeEach(() => vi.mocked(toast.warning).mockClear());

describe('useFeatureIconDropToast', () => {
  it('warns once on the move from none dropped to some, and again only when more drop', () => {
    const { rerender } = renderHook(({ dropped }) => useFeatureIconDropToast(dropped), {
      initialProps: { dropped: 0 },
    });
    expect(toast.warning).not.toHaveBeenCalled();

    rerender({ dropped: 1 });
    expect(toast.warning).toHaveBeenCalledTimes(1);
    expect(vi.mocked(toast.warning).mock.calls[0][0]).toBe(
      '1 feature icon does not fit its box and will not print. Widen the box or make the icons smaller.',
    );

    rerender({ dropped: 1 });
    expect(toast.warning).toHaveBeenCalledTimes(1);

    rerender({ dropped: 2 });
    expect(toast.warning).toHaveBeenCalledTimes(2);

    rerender({ dropped: 1 });
    rerender({ dropped: 0 });
    expect(toast.warning).toHaveBeenCalledTimes(2);

    rerender({ dropped: 1 });
    expect(toast.warning).toHaveBeenCalledTimes(3);
  });

  it('says nothing for a template that already drops icons when it opens', () => {
    renderHook(() => useFeatureIconDropToast(2));
    expect(toast.warning).not.toHaveBeenCalled();
  });
});
