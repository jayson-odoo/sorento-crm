/**
 * The catalogue upload dialog (CATALOG-IMAGES, AC-2, AC-3): PDF only, 50 MB, refused on the
 * client with a plain message; a good file goes up, the drawer opens, the review page opens.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const nav = vi.hoisted(() => ({ push: vi.fn() }));
const toasts = vi.hoisted(() => ({ error: vi.fn() }));
const drawer = vi.hoisted(() => ({ notify: vi.fn() }));
const upload = vi.hoisted(() => ({ fn: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: nav.push }) }));
vi.mock('@/lib/toast', () => ({ toast: { error: toasts.error, success: vi.fn() } }));
vi.mock('@/components/upload-activity', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued: drawer.notify }),
}));
vi.mock('../services/catalogPhotoReadingService', () => ({
  uploadCatalogPhotoReading: (...a: unknown[]) => upload.fn(...a),
}));

import { CatalogueUploadDialog } from './CatalogueUploadDialog';

function file(name: string, size = 10, type = 'application/pdf'): File {
  const f = new File(['x'], name, { type });
  Object.defineProperty(f, 'size', { value: size });
  return f;
}

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <CatalogueUploadDialog open onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

const choose = (f: File) =>
  fireEvent.change(screen.getByLabelText('Catalogue PDF'), { target: { files: [f] } });
const submit = () => screen.getByRole('button', { name: /Read catalogue/ });

beforeEach(() => {
  nav.push.mockReset();
  toasts.error.mockReset();
  drawer.notify.mockReset();
  upload.fn.mockReset();
});

describe('CatalogueUploadDialog', () => {
  it('refuses a non-PDF and keeps the submit button disabled', () => {
    renderDialog();
    choose(file('prices.xlsx', 10, 'application/vnd.ms-excel'));
    expect(toasts.error).toHaveBeenCalledWith(expect.stringContaining('not a PDF'));
    expect(submit()).toBeDisabled();
  });

  it('refuses a file over 50 MB', () => {
    renderDialog();
    choose(file('big.pdf', 51 * 1024 * 1024));
    expect(toasts.error).toHaveBeenCalledWith(expect.stringContaining('50 MB'));
    expect(submit()).toBeDisabled();
  });

  it('uploads a PDF, opens the drawer and lands on the review page', async () => {
    upload.fn.mockResolvedValue({ id: 'reading-1' });
    renderDialog();
    choose(file('catalogue.pdf', 1024));
    expect(submit()).toBeEnabled();
    fireEvent.click(submit());
    await waitFor(() => expect(nav.push).toHaveBeenCalled());
    expect(upload.fn.mock.calls[0][0].name).toBe('catalogue.pdf');
    expect(drawer.notify).toHaveBeenCalled();
    expect(nav.push).toHaveBeenCalledWith('/master-data-management/products/catalogue-photos/reading-1');
  });
});
