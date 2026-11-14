/**
 * SPEC-SHEET-PARITY-B2 v3 editor, AC-C6.1: the spec sheet has ONE font dialog, owned by the reader,
 * which both the toolbar format row and the Inspector open. Given `onManageFonts`, the Inspector's
 * Manage fonts asks the host and renders no dialog of its own. Written test-FIRST; harness as in
 * `ReaderInspector.fonts.test.tsx`.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

if (!(globalThis as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn(async () => ({
    pending: null,
    last_outcome: null,
  })),
}));
// v3 fix round (AC-C6.2): Manage fonts needs dealer_kit.library.manage.
const granted = vi.hoisted(() => ({ slugs: new Set<string>(['dealer_kit.library.manage']) }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.slugs.has(slug),
}));
vi.mock('@/app/(protected)/dealer-kit/services/assetService', () => ({
  uploadAsset: vi.fn(),
  renameAsset: vi.fn(),
  listAssets: vi.fn(async () => []),
  listFontAssets: vi.fn(async () => []),
}));

const library = vi.hoisted(() => ({
  remember: vi.fn(),
  reload: vi.fn(async () => undefined),
  rename: vi.fn(),
  forget: vi.fn(),
}));
vi.mock(
  '@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings',
  () => ({
    useKitLibrary: () => ({
      assetUrls: {},
      thumbUrls: {},
      fonts: [{ id: 'font-1', name: 'Brand Serif', kind: 'font', url: '' }],
      specKeys: [],
      fontOptions: [{ value: 'Brand Serif', label: 'Brand Serif' }],
      ...library,
    }),
  }),
);
vi.mock(
  '@/app/(protected)/dealer-kit/tag-templates/components/InspectorPanel',
  () => ({
    InspectorPanel: ({ onUploadFont }: { onUploadFont?: () => void }) => (
      <div data-testid="inspector">
        {onUploadFont && (
          <button type="button" onClick={onUploadFont}>
            Manage fonts
          </button>
        )}
      </div>
    ),
  }),
);

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { ReaderInspector } from './ReaderInspector';

const LAYER = {
  id: 'title',
  type: 'text',
  x_mm: 0,
  y_mm: 0,
  width_mm: 50,
  height_mm: 10,
  rotation_deg: 0,
  z_index: 1,
  visible: true,
  props: { kind: 'text', text: 'Title', fontFamily: 'DM Sans', fontSize: 12, color: '#000', align: 'left' },
} as unknown as TagLayer;

describe('one font dialog for the spec sheet (AC-C6.1, the toolbar and the Inspector share it)', () => {
  it('given the host font dialog, Manage fonts asks the host and opens no dialog of its own', async () => {
    const onManageFonts = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ReaderInspector
          pageKey="k1"
          layer={LAYER}
          layers={[LAYER]}
          controller={{ updateLayer: vi.fn(), updateLayerProps: vi.fn() } as never}
          mode="page"
          onModeChange={vi.fn()}
          onApplyAll={vi.fn()}
          onManageFonts={onManageFonts}
        />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Manage fonts' }));
    expect(onManageFonts).toHaveBeenCalledTimes(1);
    await Promise.resolve();
    expect(screen.queryByRole('dialog', { name: 'Brand fonts' })).toBeNull();
  });

  it('without dealer_kit.library.manage there is no Manage fonts at all (AC-C6.2)', () => {
    granted.slugs = new Set();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ReaderInspector
          pageKey="k1"
          layer={LAYER}
          layers={[LAYER]}
          controller={{ updateLayer: vi.fn(), updateLayerProps: vi.fn() } as never}
          mode="page"
          onModeChange={vi.fn()}
          onApplyAll={vi.fn()}
          onManageFonts={vi.fn()}
        />
      </QueryClientProvider>,
    );
    expect(screen.queryByRole('button', { name: 'Manage fonts' })).toBeNull();
    granted.slugs = new Set(['dealer_kit.library.manage']);
  });
});
