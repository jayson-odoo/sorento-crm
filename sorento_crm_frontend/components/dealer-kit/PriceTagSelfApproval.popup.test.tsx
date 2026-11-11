/**
 * PRICETAG-REQUEST-LAYOUT, owner hand test 11 Nov: on the request page the salesperson's own
 * proof opens from Preview in the shared lightbox; Approve is the popup's main button.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';

const toasts = vi.hoisted(() => ({ info: vi.fn(), error: vi.fn(), success: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

vi.mock('@/components/dealer-kit/DesignLightbox', () => ({
  __esModule: true,
  default: ({ footer, title }: { footer?: React.ReactNode; title: string }) => (
    <div role="dialog" aria-label={title}>
      {footer}
    </div>
  ),
}));

import { PriceTagSelfApproval } from './PriceTagSelfApproval';

const TEMPLATE = { id: 'tpl', name: 'T', family: 'art_basin', doc: { layers: [], width_mm: 80, height_mm: 50 }, print_size: { width_mm: 80, height_mm: 50 } };
const REQUEST = {
  id: 'req-1',
  doc_number: 'PT-ZZT-0001',
  lines: [
    { id: 'line-1', line_type: 'product', product_id: 'p-1', product_set_id: null, code: 'ZZTWB501', name: 'ZZT Basin', quantity: 1, tags: [{ id: 'tag-1', quantity: 1 }] },
  ],
};

function preview(withTemplate: boolean) {
  return vi.fn(async () => ({
    lines: [{ line_id: 'line-1', tag_id: 'tag-1', code: 'ZZTWB501', name: 'ZZT Basin', images: [] }],
    templates: withTemplate ? { 'line-1': TEMPLATE } : {},
    assets: {},
    images: {},
    fonts: [],
  }));
}

function renderPopup(loadPreview: ReturnType<typeof preview>, onOpenChange = vi.fn()) {
  const onApprove = vi.fn(async (_doc: unknown) => {});
  const onEscalate = vi.fn(async () => {});
  render(
    <PriceTagSelfApproval
      request={REQUEST as never}
      loadPreview={loadPreview as never}
      onApprove={onApprove}
      onEdit={vi.fn()}
      onEscalate={onEscalate}
      popup={{ open: true, onOpenChange }}
    />,
  );
  return { onApprove, onEscalate, onOpenChange };
}

describe('PriceTagSelfApproval in popup mode', () => {
  it('Approve sends the sheet it drew; there is no Edit inside the popup', async () => {
    const { onApprove } = renderPopup(preview(true));
    const approve = await screen.findByRole('button', { name: /^approve$/i });
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(screen.getByRole('button', { name: /escalate to marketing/i })).toBeInTheDocument();
    fireEvent.click(approve);
    await waitFor(() => expect(onApprove).toHaveBeenCalledTimes(1));
    expect(onApprove.mock.calls[0][0]).toHaveProperty('sheets');
  });

  it('with no template nothing can be drawn: it says so and closes, no empty popup', async () => {
    const { onOpenChange } = renderPopup(preview(false));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(toasts.info).toHaveBeenCalledWith(expect.stringMatching(/No tag template yet/));
    expect(screen.queryByRole('button', { name: /^approve$/i })).toBeNull();
  });

  it('renders nothing while closed, even once the tag has loaded', async () => {
    const load = preview(true);
    render(
      <PriceTagSelfApproval
        request={REQUEST as never}
        loadPreview={load as never}
        onApprove={vi.fn()}
        onEdit={vi.fn()}
        onEscalate={vi.fn()}
        popup={{ open: false, onOpenChange: vi.fn() }}
      />,
    );
    await waitFor(() => expect(load).toHaveBeenCalled());
    await act(async () => {});
    // The lightbox stand-in draws whenever it is rendered, so any render while closed shows here.
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
