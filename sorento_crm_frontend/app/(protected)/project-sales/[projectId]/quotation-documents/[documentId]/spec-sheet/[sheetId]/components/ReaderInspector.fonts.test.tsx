/**
 * SPEC-SHEET-PARITY-B2 v3 editor, AC-C6.1: the spec sheet Inspector's Font Family offers "Manage
 * fonts", which opens the template designer's own `FontUploadDialog` ("Brand fonts") on the ONE kit
 * library, so a font uploaded here is selectable at once in both designers. Written test-FIRST.
 *
 * The InspectorPanel stand-in renders "Manage fonts" only when it is handed `onUploadFont`, exactly
 * as the real one does (`InspectorPanel.tsx` Typography block).
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
  props: {
    kind: 'text',
    text: 'Title',
    fontFamily: 'DM Sans',
    fontSize: 12,
    color: '#000',
    align: 'left',
  },
} as unknown as TagLayer;

function mount() {
  // The app always has a QueryClient; the font dialog's rows use it (deferred delete).
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <ReaderInspector
        pageKey="k1"
        layer={LAYER}
        layers={[LAYER]}
        controller={
          { updateLayer: vi.fn(), updateLayerProps: vi.fn() } as never
        }
        mode="page"
        onModeChange={vi.fn()}
        onApplyAll={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

describe('Manage fonts on the spec sheet Inspector (AC-C6.1)', () => {
  it('is offered next to Font Family', () => {
    mount();
    expect(
      screen.getByRole('button', { name: 'Manage fonts' }),
    ).toBeInTheDocument();
  });

  it('opens the template designer font dialog listing the kit fonts', async () => {
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Manage fonts' }));
    const dialog = await screen.findByRole('dialog', { name: 'Brand fonts' });
    expect(dialog).toHaveTextContent('Brand Serif');
  });
});
