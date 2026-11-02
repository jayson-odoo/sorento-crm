/** PRICETAG-SELF-APPROVAL R3/R6: Approve sends the sheet on screen; Escalate needs a note. */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';

vi.mock('@/components/dealer-kit/DesignViewer', () => ({
  __esModule: true,
  default: ({
    payload,
    emptyMessage,
    headerActions,
    footer,
  }: {
    payload: unknown;
    emptyMessage: string;
    headerActions?: ReactNode;
    footer?: ReactNode;
  }) => (
    <div>
      <div data-testid="viewer">{payload ? 'drawn' : emptyMessage}</div>
      {headerActions}
      {footer}
    </div>
  ),
}));

import { PriceTagSelfApproval } from './PriceTagSelfApproval';
import type {
  PriceTagRequestLine,
  TagPreviewResponse,
} from '@/app/(auth)/portal/lib/price-tag-request-service';

const line = {
  id: 'l1',
  line_type: 'product',
  product_id: 'p1',
  product_set_id: null,
  name: 'Basin',
  code: 'B-1',
  show_promo_price: false,
  quantity: 1,
  included_accessories: null,
  remarks: null,
  sort_order: 0,
  tags: [{ id: 't1', label: '1a', quantity: 1 }],
} as PriceTagRequestLine;

const preview = {
  lines: [{ line_id: 'l1', tag_id: 't1', code: 'B-1', name: 'Basin', images: [] }],
  templates: {
    l1: {
      id: 'tpl',
      name: 'Basin A5',
      family: 'ala_carte',
      doc: { layers: [], width_mm: 80, height_mm: 50 },
      print_size: { width_mm: 80, height_mm: 50 },
    },
  },
  assets: {},
  images: {},
  fonts: [],
} as unknown as TagPreviewResponse;

function renderIt(overrides: Partial<Parameters<typeof PriceTagSelfApproval>[0]> = {}) {
  const props = {
    request: { id: 'r1', doc_number: 'PT-1', lines: [line] },
    loadPreview: vi.fn().mockResolvedValue(preview),
    onApprove: vi.fn().mockResolvedValue(undefined),
    onEdit: vi.fn(),
    onEscalate: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  render(<PriceTagSelfApproval {...props} />);
  return props;
}

describe('PriceTagSelfApproval', () => {
  it('approves the sheet it drew, placed on the request\'s own tag', async () => {
    const props = renderIt();
    await waitFor(() => expect(screen.getByTestId('viewer')).toHaveTextContent('drawn'));

    fireEvent.click(screen.getByRole('button', { name: /approve/i }));

    await waitFor(() => expect(props.onApprove).toHaveBeenCalledTimes(1));
    const doc = props.onApprove.mock.calls[0][0];
    const placed = doc.sheets.flatMap((s: { tags: { request_tag_id: string }[] }) => s.tags);
    expect(new Set(placed.map((t: { request_tag_id: string }) => t.request_tag_id))).toEqual(
      new Set(['t1']),
    );
  });

  it('cannot approve when nothing could be drawn', async () => {
    renderIt({ loadPreview: vi.fn().mockRejectedValue(new Error('down')) });
    await waitFor(() => expect(screen.getByTestId('viewer')).toHaveTextContent('Tag unavailable'));

    expect(screen.getByRole('button', { name: /approve/i })).toBeDisabled();
  });

  it('escalates only with a note', async () => {
    const props = renderIt();
    fireEvent.click(screen.getByRole('button', { name: /escalate to marketing/i }));
    const send = screen.getByRole('button', { name: /send to marketing/i });
    expect(send).toBeDisabled();

    fireEvent.change(screen.getByLabelText('What marketing needs to fix'), {
      target: { value: 'Photo is the old model' },
    });
    fireEvent.click(send);

    await waitFor(() => expect(props.onEscalate).toHaveBeenCalledWith('Photo is the old model'));
  });

  it('Edit opens the revise composer', () => {
    const props = renderIt();
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    expect(props.onEdit).toHaveBeenCalled();
  });
});
