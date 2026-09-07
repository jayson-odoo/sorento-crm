/**
 * ShipmentLinePhotosCell - thumbnail strip, the add-photos dialog, preview, and the
 * deferred (D7) per-thumbnail delete (R25, purchasing consolidation batch, lane C,
 * slice C3, review round 1). The upload goes through `useUploadShipmentLinePhotos`
 * (`useFulfilment.ts`), which calls `uploadShipmentLinePhotos` - mocked at the
 * service layer below so the hook's own dispatch is exercised for real.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// AttachmentPreviewModal's carousel (embla) reads both in jsdom.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
class IntersectionObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver =
  IntersectionObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const uploadShipmentLinePhotos = vi.fn().mockResolvedValue([]);
vi.mock('@/app/(protected)/scm/services/fulfilmentService', () => ({
  uploadShipmentLinePhotos: (...args: unknown[]) => uploadShipmentLinePhotos(...args),
}));

const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pa-1',
  action_key: 'shipment_line_photo.delete',
  entity_type: 'shipment_line_photo',
  entity_id: 'photo-1',
  commit_at: '2026-09-06T10:00:10',
  window_seconds: 10,
});
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

import { ShipmentLinePhotosCell } from './ShipmentLinePhotosCell';
import type { ShipmentLinePhoto } from '@/app/(protected)/scm/services/fulfilmentService';

function photo(over: Partial<ShipmentLinePhoto> = {}): ShipmentLinePhoto {
  return {
    id: 'photo-1',
    attachment_id: 'att-1',
    sort_order: 1,
    thumbnail_url: 'https://cdn.example.com/thumb.jpg',
    url: 'https://cdn.example.com/full.jpg',
    filename: 'container-side.jpg',
    ...over,
  };
}

function makeFile(name: string): File {
  return new File(['x'], name, { type: 'image/jpeg' });
}

function renderCell(photos: ShipmentLinePhoto[] = []) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ShipmentLinePhotosCell
        shipmentId="shipment-1"
        lineId="line-1"
        productLabel="SRTWC286-SH"
        photos={photos}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  uploadShipmentLinePhotos.mockResolvedValue([]);
});

describe('ShipmentLinePhotosCell', () => {
  it('renders a thumbnail per photo and the add button', () => {
    renderCell([photo()]);

    expect(
      screen.getByRole('button', { name: 'View container-side.jpg for SRTWC286-SH' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add photos for SRTWC286-SH' }),
    ).toBeInTheDocument();
  });

  it('collapses beyond four photos into a "+n" badge', () => {
    const photos = Array.from({ length: 6 }, (_, i) =>
      photo({ id: `photo-${i}`, filename: `p${i}.jpg` }),
    );
    renderCell(photos);

    expect(screen.getByText('+2')).toBeInTheDocument();
  });

  it('shows "Save the line first" when the line has no id yet', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ShipmentLinePhotosCell
          shipmentId="shipment-1"
          lineId={null}
          productLabel="new line"
          photos={[]}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByText('Save the line first')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add photos/ })).not.toBeInTheDocument();
  });

  it('opens the dropzone dialog and uploads the picked files', async () => {
    renderCell([]);

    fireEvent.click(screen.getByRole('button', { name: 'Add photos for SRTWC286-SH' }));
    expect(await screen.findByText('Add photos - SRTWC286-SH')).toBeInTheDocument();

    const zone = screen.getByRole('button', { name: /drop|browse|choose/i });
    fireEvent.drop(zone, { dataTransfer: { files: [makeFile('new-photo.jpg')] } });

    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));

    await waitFor(() =>
      expect(uploadShipmentLinePhotos).toHaveBeenCalledWith(
        'shipment-1',
        'line-1',
        expect.arrayContaining([expect.objectContaining({ name: 'new-photo.jpg' })]),
      ),
    );
  });

  it('opens the preview modal on a thumbnail click', () => {
    renderCell([photo()]);

    fireEvent.click(
      screen.getByRole('button', { name: 'View container-side.jpg for SRTWC286-SH' }),
    );

    expect(screen.getByText('container-side.jpg')).toBeInTheDocument();
  });

  it('parks the delete on hover-x with no confirmation dialog in the way (D7)', async () => {
    renderCell([photo()]);

    fireEvent.click(
      screen.getByRole('button', { name: 'Delete container-side.jpg for SRTWC286-SH' }),
    );

    await waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionKey: 'shipment_line_photo.delete',
          entityType: 'shipment_line_photo',
          entityId: 'photo-1',
        }),
      ),
    );
    expect(screen.queryByText('Confirm delete')).not.toBeInTheDocument();
  });
});
