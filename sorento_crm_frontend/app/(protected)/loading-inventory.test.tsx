/**
 * S7-04 - inventory of the ten busiest lists that now hold their shape while
 * they load. Each module below is a route-level `loading.tsx`; Next.js renders
 * it in place of the segment's children while that segment's chunk and first
 * page are in flight, INSIDE `app/(protected)/layout.tsx` (sidebar + header
 * stay put). This test does not re-verify that Next.js behaviour - it pins
 * down the list this slice claims to cover, so a future refactor that removes
 * one of the ten fails loudly here rather than silently regressing a list
 * nobody is looking at that day.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const TEN_LOADING_MODULES = [
  './forms-management/forms/loading',
  './order-management/orders/loading',
  './marketing-management/promotions/loading',
  './user-management/users/loading',
  './user-management/contact-access-agents/loading',
  './system-management/import-jobs/loading',
  './procurement-management/spo-allocations/loading',
  './resource-management/attachment-directories/loading',
  './master-data-management/products/loading',
  './complaint-management/complaints/loading',
] as const;

describe('the ten list loading.tsx files (S7-04)', () => {
  it('all ten exist and each renders the shared ListPageSkeleton', async () => {
    expect(TEN_LOADING_MODULES).toHaveLength(10);

    for (const path of TEN_LOADING_MODULES) {
      // A missing file throws on import - that is the assertion for "exists".
      const mod = await import(/* @vite-ignore */ path);
      const Loading = mod.default;
      expect(typeof Loading).toBe('function');

      const { container, unmount } = render(<Loading />);
      // Content-only: no shell wrapper of its own.
      expect(container.querySelector('[role="status"]')).not.toBeInTheDocument();
      expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
      unmount();
    }
  });
});
