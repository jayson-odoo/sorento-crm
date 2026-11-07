/**
 * PRICETAG-ACCESSORY-DESIGNER S5: the delete is the server-deferred pending action
 * `accessory_box_preset.delete` (no confirm dialog), like `useDeleteTagSizePreset`.
 * Written test-FIRST: the hooks file does not exist yet.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const deferred = vi.hoisted(() => vi.fn(() => ({ run: vi.fn() })));
vi.mock('@/hooks/useDeferredRowAction', () => ({ useDeferredRowAction: deferred }));
vi.mock('../../services/accessoryTemplateService', () => ({
  listAccessoryTemplates: vi.fn(async () => []),
  getAccessoryTemplate: vi.fn(),
  createAccessoryTemplate: vi.fn(),
  updateAccessoryTemplate: vi.fn(),
  getAccessoryTemplateUsage: vi.fn(),
}));

import { useDeleteAccessoryTemplate } from './useAccessoryTemplates';

describe('useDeleteAccessoryTemplate', () => {
  it('parks accessory_box_preset.delete for the accessory_box_preset entity', () => {
    renderHook(() => useDeleteAccessoryTemplate(), {
      wrapper: ({ children }) => <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>,
    });
    expect(deferred).toHaveBeenCalledWith(
      expect.objectContaining({
        actionKey: 'accessory_box_preset.delete',
        entityType: 'accessory_box_preset',
      }),
    );
  });
});
