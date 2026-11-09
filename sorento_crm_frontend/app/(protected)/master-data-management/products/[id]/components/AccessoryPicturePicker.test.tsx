/**
 * PRICETAG-ACC-PICTURE-PICKER (owner, 9 Nov): the pencil dialog's Picture choice shows a thumbnail
 * in every option and in the selected value, and the row thumbnail follows the chosen picture the
 * moment Save is pressed (no reload, no refetch).
 *
 * Plan: documentation/plans/dealer-kit/PLAN-pricetag-acc-picture-picker-09nov.md. Written test-FIRST.
 *
 * Contract:
 *  - a picture carries `thumb_url` (the 320 px rendition) beside `url` (the original).
 *  - the Picture choice renders through `SearchableSelect`'s `renderOption` / `renderTriggerLabel`,
 *    each showing the shared `AttachmentImage` (an <img> of the thumb) next to the label.
 *  - the row thumbnail is the picture `entry.image_id` names, else the accessory's own first.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { AccessoryEntry } from '../../../accessories/types/accessory.types';

const service = vi.hoisted(() => ({
  listOwnerAccessories: vi.fn(),
  replaceOwnerAccessories: vi.fn(),
  searchAccessories: vi.fn(),
  createAccessory: vi.fn(),
}));
vi.mock('../../../accessories/services/accessoryService', () => service);
vi.mock('../../services/productService', () => ({ getProducts: vi.fn(async () => ({ data: [] })) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/ui/rich-text-editor', () => {
  const Stand = (props: { value?: string; onChange: (v: string) => void }) => (
    <textarea data-testid="rte" value={props.value ?? ''} onChange={(e) => props.onChange(e.target.value)} />
  );
  return { RichTextEditor: Stand, default: Stand };
});

type Opt = { value: string; label: string };
// A plain stand-in that still draws the caller's renderOption / renderTriggerLabel, so the test reads
// what the real picker would show in its list and in its trigger.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value?: string | null;
    onChange: (v: string) => void;
    options?: Opt[];
    'aria-label'?: string;
    renderOption?: (o: Opt) => React.ReactNode;
    renderTriggerLabel?: (o: Opt) => React.ReactNode;
  }) => {
    const opts = props.options ?? [];
    const selected = opts.find((o) => o.value === props.value);
    return (
      <div>
        <div data-testid={`${props['aria-label']} trigger`}>
          {selected ? (props.renderTriggerLabel ? props.renderTriggerLabel(selected) : selected.label) : null}
        </div>
        <ul data-testid={`${props['aria-label']} options`}>
          {opts.map((o) => (
            <li key={o.value}>
              <button type="button" onClick={() => props.onChange(o.value)}>
                {props.renderOption ? props.renderOption(o) : o.label}
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  },
}));

import { AccessoryListField } from './AccessoryListField';

const P1 = { id: 'i1', attachment_id: 'att1', url: 'https://cdn.test/1.png', thumb_url: 'https://cdn.test/1.png.thumb.jpg', colour_name: null, colour_hex: null };
const P2 = { id: 'i2', attachment_id: 'att2', url: 'https://cdn.test/2.png', thumb_url: 'https://cdn.test/2.png.thumb.jpg', colour_name: null, colour_hex: null };
const NONE = { image_id: null, name: null, spec: null, remark: null };

// As the server sends it: `image` is the accessory's OWN first picture; the row's pick is in `entry`.
const colander = (imageId: string | null) =>
  ({
    kind: 'accessory',
    code: null,
    list_price: null,
    id: 'a1',
    name: 'COLANDER',
    spec: null,
    remark: null,
    image: { attachment_id: 'att1', url: P1.url },
    images: [P1, P2],
    entry: { ...NONE, image_id: imageId },
    product_count: 0,
    combo_count: 0,
  }) as unknown as AccessoryEntry;

function mount() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AccessoryListField kind="product" ownerId="p1" label="Accessories included" canEdit />
    </QueryClientProvider>,
  );
}

const rowImage = () => {
  const list = screen.getByRole('list', { name: 'Accessories included' });
  return list.querySelector('img') as HTMLImageElement;
};

beforeEach(() => {
  vi.clearAllMocks();
  service.listOwnerAccessories.mockResolvedValue([colander(null)]);
  service.searchAccessories.mockResolvedValue([]);
});

describe('Picture choice thumbnails', () => {
  it('every option shows a thumbnail of its picture beside its label', async () => {
    mount();
    await screen.findByText('COLANDER');
    fireEvent.click(screen.getByRole('button', { name: 'Edit for this list' }));
    const dialog = await screen.findByRole('dialog');
    const options = within(dialog).getByTestId('Picture choice options');
    const items = within(options).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('Picture 1');
    expect(items[1]).toHaveTextContent('Picture 2');
    const thumbs = items.map((item) => item.querySelector('img') as HTMLImageElement);
    // The rendition, never the original.
    expect(thumbs.map((img) => img.getAttribute('src'))).toEqual([P1.thumb_url, P2.thumb_url]);
  });

  it('the selected value shows its thumbnail too', async () => {
    service.listOwnerAccessories.mockResolvedValue([colander('i2')]);
    mount();
    await screen.findByText('COLANDER');
    fireEvent.click(screen.getByRole('button', { name: 'Edit for this list' }));
    const dialog = await screen.findByRole('dialog');
    const trigger = within(dialog).getByTestId('Picture choice trigger');
    expect(trigger).toHaveTextContent('Picture 2');
    expect(trigger.querySelector('img')).toHaveAttribute('src', P2.thumb_url);
  });
});

describe('the row follows the chosen picture', () => {
  it('shows the row pick on load, not the accessory own first picture', async () => {
    service.listOwnerAccessories.mockResolvedValue([colander('i2')]);
    mount();
    await screen.findByText('COLANDER');
    expect(rowImage()).toHaveAttribute('src', P2.thumb_url);
  });

  it('changes the row thumbnail right after Save, with no refetch', async () => {
    // The server answers the way it really does: own `image` unchanged, the pick in `entry`.
    let answer: (rows: AccessoryEntry[]) => void = () => {};
    service.replaceOwnerAccessories.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    mount();
    await screen.findByText('COLANDER');
    expect(rowImage()).toHaveAttribute('src', P1.thumb_url);

    fireEvent.click(screen.getByRole('button', { name: 'Edit for this list' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(within(dialog).getByTestId('Picture choice options')).getByText('Picture 2'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));

    // Optimistic: before the server has answered.
    await waitFor(() => expect(rowImage()).toHaveAttribute('src', P2.thumb_url));
    answer([colander('i2')]);
    await waitFor(() => expect(service.replaceOwnerAccessories).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(rowImage()).toHaveAttribute('src', P2.thumb_url));
    expect(service.listOwnerAccessories).toHaveBeenCalledTimes(1);
  });
});

describe('the row goes back to the accessory own picture', () => {
  it("Use the accessory's own + Save shows the first picture again", async () => {
    service.listOwnerAccessories.mockResolvedValue([colander('i2')]);
    service.replaceOwnerAccessories.mockReturnValue(new Promise(() => {}));
    mount();
    await screen.findByText('COLANDER');
    expect(rowImage()).toHaveAttribute('src', P2.thumb_url);
    fireEvent.click(screen.getByRole('button', { name: 'Edit for this list' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: "Use the accessory's own" }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(rowImage()).toHaveAttribute('src', P1.thumb_url));
  });
});
