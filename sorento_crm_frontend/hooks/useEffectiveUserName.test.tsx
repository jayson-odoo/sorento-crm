/**
 * QUOTE-ATTN-PICKER owner ruling (11 Nov 2026): Prepared By is whoever creates the document. A new
 * quotation's form shows the effective user, which is the impersonated user during a view-as,
 * because the backend saves created_by as that user.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'admin-1', name: 'Test Admin' } }, status: 'authenticated' }),
}));

import { impersonationStore } from '@/lib/impersonation-store';
import { useEffectiveUserName } from './useEffectiveUserId';

afterEach(() => impersonationStore.setSession(null));

describe('useEffectiveUserName', () => {
  it('is the signed-in user outside a view-as', () => {
    const { result } = renderHook(() => useEffectiveUserName());
    expect(result.current).toBe('Test Admin');
  });

  it('is the impersonated user during a view-as', () => {
    impersonationStore.setSession({
      sessionId: 'imp-1',
      startedAt: '2026-11-11T00:00:00Z',
      targetUser: { id: 'u-9', name: 'Test Salesperson B', email: 't@x.test', avatar: null, role_name: null },
    });
    const { result } = renderHook(() => useEffectiveUserName());
    expect(result.current).toBe('Test Salesperson B');
  });
});
