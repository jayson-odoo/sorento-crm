/**
 * PRICETAG-ACCESSORY-DESIGNER S4: the pencil on a list row sets per-list overrides: which picture,
 * name, spec lines and remark (blank = the accessory's own).
 *
 * Plan: PLAN-pricetag-accessory-designer-07nov.md "S4 Master data" and "List entries". Written test-FIRST.
 *
 * Contract assumed:
 *  - an entry from the API carries `images: [{ id, attachment_id, url, colour_name, colour_hex }]` and
 *    `entry: { image_id, name, spec, remark }`.
 *  - the pencil is a button with aria-label "Edit for this list" on every row (editors only), opening a
 *    dialog with "Picture choice" (only when the accessory has more than one picture), "Name",
 *    "Spec lines", "Remark", a "Use the accessory's own" button and Save.
 *  - Save writes the whole list through `replaceOwnerAccessories(kind, id, items)` where the edited row is
 *    `{ accessory_id, image_id, name, spec, remark }`. A row that has no overrides stays `{ accessory_id }`.
 *  - a row with any override shows the pill "Own text".
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
// A native select stands in for the Radix picker (options or fetchOptions).
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value?: string | null;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    fetchOptions?: (q: string, p: number) => Promise<{ value: string; label: string }[]>;
    'aria-label'?: string;
  }) => {
    const [fetched, setFetched] = React.useState<{ value: string; label: string }[]>([]);
    React.useEffect(() => {
      void props.fetchOptions?.('', 0).then(setFetched);
    }, []);
    const opts = props.options ?? fetched;
    return (
      <select aria-label={props['aria-label']} value={props.value ?? ''} onChange={(e) => props.onChange(e.target.value)}>
        <option value="" />
        {opts.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  },
}));

import { AccessoryListField } from './AccessoryListField';

const BLACK = { id: 'i1', attachment_id: 'att1', url: 'https://cdn.test/b.jpg', colour_name: 'Black', colour_hex: '#1f2937' };
const GREY = { id: 'i2', attachment_id: 'att2', url: 'https://cdn.test/g.jpg', colour_name: 'Grey', colour_hex: '#9ca3af' };
const NONE = { image_id: null, name: null, spec: null, remark: null };

const entry = (id: string, name: string, extra: Record<string, unknown> = {}) =>
  ({
    kind: 'accessory',
    code: null,
    list_price: null,
    id,
    name,
    spec: null,
    remark: null,
    image: null,
    images: [],
    entry: NONE,
    product_count: 0,
    combo_count: 0,
    ...extra,
  }) as unknown as AccessoryEntry;

const COLANDER = entry('a1', 'COLANDER', { spec: '390x200x140', image: { attachment_id: 'att1', url: BLACK.url }, images: [BLACK, GREY] });
const BOARD = entry('a2', 'CHOPPING BOARD', { images: [{ ...BLACK, id: 'i9', attachment_id: 'att9' }] });

function mount(canEdit = true) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AccessoryListField kind="product" ownerId="p1" label="Accessories" canEdit={canEdit} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  service.listOwnerAccessories.mockResolvedValue([COLANDER, BOARD]);
  service.searchAccessories.mockResolvedValue([]);
  service.replaceOwnerAccessories.mockResolvedValue([COLANDER, BOARD]);
});

describe('AccessoryListField overrides', () => {
  it('every row has an Edit for this list pencil', async () => {
    mount();
    await screen.findByText('COLANDER');
    expect(screen.getAllByRole('button', { name: 'Edit for this list' })).toHaveLength(2);
  });

  it('read-only readers get no pencil', async () => {
    const view = mount(false);
    await screen.findByText('COLANDER');
    expect(screen.queryByRole('button', { name: 'Edit for this list' })).toBeNull();
    view.unmount();
    mount(true);
    await screen.findByText('COLANDER');
    expect(screen.getAllByRole('button', { name: 'Edit for this list' }).length).toBeGreaterThan(0);
  });

  it('the dialog offers Picture choice for an accessory with several pictures, plus Name, Spec lines, Remark', async () => {
    mount();
    await screen.findByText('COLANDER');
    fireEvent.click(screen.getAllByRole('button', { name: 'Edit for this list' })[0]);
    const dialog = await screen.findByRole('dialog');
    const choice = within(dialog).getByLabelText('Picture choice') as HTMLSelectElement;
    expect(Array.from(choice.querySelectorAll('option')).map((o) => o.textContent)).toEqual(
      expect.arrayContaining(['Black', 'Grey']),
    );
    expect(within(dialog).getByLabelText('Name')).toBeInTheDocument();
    expect(within(dialog).getByText('Spec lines')).toBeInTheDocument();
    expect(within(dialog).getByText('Remark')).toBeInTheDocument();
    expect(within(dialog).getAllByTestId('rte')).toHaveLength(2);
  });

  it('an accessory with one picture has no Picture choice', async () => {
    mount();
    await screen.findByText('CHOPPING BOARD');
    fireEvent.click(screen.getAllByRole('button', { name: 'Edit for this list' })[1]);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).queryByLabelText('Picture choice')).toBeNull();
    expect(within(dialog).getByLabelText('Name')).toBeInTheDocument();
  });

  it('Save writes the whole list with the overrides on the edited row only', async () => {
    mount();
    await screen.findByText('COLANDER');
    fireEvent.click(screen.getAllByRole('button', { name: 'Edit for this list' })[0]);
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Picture choice'), { target: { value: 'i2' } });
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'Sink colander' } });
    const [spec, remark] = within(dialog).getAllByTestId('rte');
    fireEvent.change(spec, { target: { value: 'Depth: 160mm' } });
    fireEvent.change(remark, { target: { value: 'Follows sink' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(service.replaceOwnerAccessories).toHaveBeenCalledWith('product', 'p1', [
        { accessory_id: 'a1', image_id: 'i2', name: 'Sink colander', spec: 'Depth: 160mm', remark: 'Follows sink' },
        expect.objectContaining({ accessory_id: 'a2' }),
      ]),
    );
  });

  it('a blank field is sent as no override', async () => {
    service.listOwnerAccessories.mockResolvedValue([
      entry('a1', 'COLANDER', { images: [BLACK, GREY], entry: { ...NONE, name: 'Old' } }),
    ]);
    mount();
    await screen.findByText('COLANDER');
    fireEvent.click(screen.getByRole('button', { name: 'Edit for this list' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: '   ' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(service.replaceOwnerAccessories).toHaveBeenCalled());
    const sent = service.replaceOwnerAccessories.mock.calls[0][2][0];
    expect(sent.accessory_id).toBe('a1');
    expect(sent.name ?? null).toBeNull();
  });

  it('Use the accessory\'s own clears every override', async () => {
    service.listOwnerAccessories.mockResolvedValue([
      entry('a1', 'COLANDER', { images: [BLACK, GREY], entry: { image_id: 'i2', name: 'Own', spec: 'S', remark: 'R' } }),
    ]);
    mount();
    await screen.findByText('COLANDER');
    fireEvent.click(screen.getByRole('button', { name: 'Edit for this list' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: "Use the accessory's own" }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(service.replaceOwnerAccessories).toHaveBeenCalled());
    const sent = service.replaceOwnerAccessories.mock.calls[0][2][0];
    expect(sent.accessory_id).toBe('a1');
    expect(sent.image_id ?? null).toBeNull();
    expect(sent.name ?? null).toBeNull();
    expect(sent.spec ?? null).toBeNull();
    expect(sent.remark ?? null).toBeNull();
  });

  it('a row with any override shows the Own text pill, a plain row does not', async () => {
    service.listOwnerAccessories.mockResolvedValue([
      entry('a1', 'COLANDER', { entry: { ...NONE, remark: 'Follows sink' } }),
      entry('a2', 'CHOPPING BOARD'),
    ]);
    mount();
    await screen.findByText('COLANDER');
    const rows = screen.getAllByRole('listitem');
    expect(within(rows[0]).getByText('Own text')).toBeInTheDocument();
    expect(within(rows[1]).queryByText('Own text')).toBeNull();
  });
});
