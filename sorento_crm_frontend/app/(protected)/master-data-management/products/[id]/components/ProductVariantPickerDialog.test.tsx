/**
 * Verifies the shared variant picker combobox:
 *  - renders human-readable `code — name` options, never a raw UUID,
 *  - excludes the ids it is told to hide (self + existing children),
 *  - confirms with the chosen product's id.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render,
  screen,
  cleanup,
  fireEvent,
  waitFor,
  within,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getProductsForVariantSelect = vi.fn();

vi.mock('../../services/productService', () => ({
  getProductsForVariantSelect: (...a: unknown[]) => getProductsForVariantSelect(...a),
}));

import ProductVariantPickerDialog from './ProductVariantPickerDialog';

const OPTIONS = [
  { id: 'u-parent', product_code: 'SRTKT71SS', product_name: 'Kitchen Tap 71' },
  { id: 'u-child', product_code: 'SRTKT71SS-BL', product_name: 'Kitchen Tap 71 Black' },
];

function renderPicker(props: Partial<React.ComponentProps<typeof ProductVariantPickerDialog>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onConfirm = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <ProductVariantPickerDialog
        open
        onOpenChange={onOpenChange}
        title="Set variant parent"
        description="Pick the base product this product should be a variant of."
        confirmLabel="Set parent"
        excludeIds={[]}
        onConfirm={onConfirm}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { onConfirm, onOpenChange };
}

beforeEach(() => {
  getProductsForVariantSelect.mockReset();
  getProductsForVariantSelect.mockResolvedValue(OPTIONS);
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  }
  Element.prototype.scrollIntoView = vi.fn();
  (Element.prototype as unknown as { hasPointerCapture: unknown }).hasPointerCapture =
    vi.fn();
  (Element.prototype as unknown as { setPointerCapture: unknown }).setPointerCapture =
    vi.fn();
  (
    Element.prototype as unknown as { releasePointerCapture: unknown }
  ).releasePointerCapture = vi.fn();
});

afterEach(() => cleanup());

describe('ProductVariantPickerDialog', () => {
  it('renders code — name options and never a raw UUID', async () => {
    renderPicker();

    // Open the combobox popover.
    fireEvent.click(screen.getByRole('combobox'));

    const black = await screen.findByText(/SRTKT71SS-BL — Kitchen Tap 71 Black/);
    expect(black).toBeInTheDocument();
    expect(screen.getByText(/SRTKT71SS — Kitchen Tap 71/)).toBeInTheDocument();

    // No option surfaces the underlying product UUID as visible text.
    expect(black.textContent).not.toContain('u-child');
    expect(document.body.textContent).not.toContain('u-parent');
  });

  it('hides excluded ids (self + existing children) from the options', async () => {
    renderPicker({ excludeIds: ['u-child'] });
    fireEvent.click(screen.getByRole('combobox'));

    await screen.findByText(/SRTKT71SS — Kitchen Tap 71/);
    expect(
      screen.queryByText(/SRTKT71SS-BL — Kitchen Tap 71 Black/),
    ).not.toBeInTheDocument();
  });

  it('confirms with the chosen product id', async () => {
    const { onConfirm } = renderPicker();
    fireEvent.click(screen.getByRole('combobox'));

    fireEvent.click(await screen.findByText(/SRTKT71SS — Kitchen Tap 71/));
    fireEvent.click(screen.getByRole('button', { name: /set parent/i }));

    expect(onConfirm).toHaveBeenCalledWith('u-parent');
  });
});
