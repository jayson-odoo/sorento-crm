import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const held = { set: new Set<string>() };

const loading = { value: false };

vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissionSet: held.set, isLoading: loading.value }),
}));

import { useNewProductApplicationListingKey } from './useNewProductApplications';

describe('useNewProductApplicationListingKey', () => {
  it('keys a create-only applicant by create, so column preferences are not refused', () => {
    held.set = new Set(['procurement.new_product_applications.create']);
    const { result } = renderHook(() => useNewProductApplicationListingKey('lines'));
    expect(result.current).toBe('procurement.new_product_applications.create::lines');
  });

  it('asks for no preferences until the permissions are known (no guessed 403)', () => {
    loading.value = true;
    held.set = new Set();
    const { result } = renderHook(() => useNewProductApplicationListingKey('lines'));
    expect(result.current).toBeNull();
    loading.value = false;
  });

  it('prefers view, then approve, then open_code', () => {
    held.set = new Set([
      'procurement.new_product_applications.create',
      'procurement.new_product_applications.open_code',
    ]);
    const { result } = renderHook(() => useNewProductApplicationListingKey());
    expect(result.current).toBe('procurement.new_product_applications.open_code');
  });
});
