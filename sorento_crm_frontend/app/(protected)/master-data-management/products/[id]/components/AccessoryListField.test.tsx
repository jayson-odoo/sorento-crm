import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { AccessoryEntry } from '../../../accessories/types/accessory.types';

const service = vi.hoisted(() => ({
  listOwnerAccessories: vi.fn(),
  replaceOwnerAccessories: vi.fn(),
  searchAccessories: vi.fn(),
  createAccessory: vi.fn(),
}));
vi.mock('../../../accessories/services/accessoryService', () => service);
vi.mock('../../services/productService', () => ({ getProducts: vi.fn() }));
// Captures the drag handler the component wires, so a reorder can be driven without a pointer.
const dnd = vi.hoisted(() => ({ onDragEnd: null as null | ((e: unknown) => void) }));
vi.mock('@dnd-kit/core', async (orig) => {
  const actual = await orig<typeof import('@dnd-kit/core')>();
  return {
    ...actual,
    DndContext: (props: { onDragEnd: (e: unknown) => void; children: React.ReactNode }) => {
      dnd.onDragEnd = props.onDragEnd;
      return <>{props.children}</>;
    },
  };
});
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

type Opt = { value: string; label: string; group?: string };
const pickerFetch = vi.hoisted(() => ({ current: null as null | ((q: string, p: number) => Promise<Opt[]>) }));
// The real picker is a Radix popover; a native select stands in for the pick.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    onChange: (v: string) => void;
    fetchOptions: (q: string, p: number) => Promise<Opt[]>;
    'aria-label'?: string;
  }) => {
    const [opts, setOpts] = React.useState<Opt[]>([]);
    pickerFetch.current = props.fetchOptions;
    React.useEffect(() => {
      void props.fetchOptions('', 0).then(setOpts);
    }, []);
    return (
      <select
        aria-label={props['aria-label']}
        value=""
        onChange={(e) => props.onChange(e.target.value)}
      >
        <option value="" />
        {opts.map((o) => (
          <option key={o.value} value={o.value} data-group={o.group}>
            {o.label}
          </option>
        ))}
      </select>
    );
  },
}));

import { AccessoryListField } from './AccessoryListField';
import { getProducts } from '../../services/productService';

const acc = (id: string, name: string, extra: Partial<AccessoryEntry> = {}): AccessoryEntry => ({
  kind: 'accessory',
  code: null,
  list_price: null,
  id,
  name,
  spec: null,
  image: null,
  product_count: 0,
  combo_count: 0,
  ...extra,
});
const TAP = acc('a1', 'Tap', { spec: 'Chrome' });
const WASTE = acc('a2', 'Waste', { image: { attachment_id: 'x', url: 'http://img/w.png' } });
const TRAP = acc('a3', 'Trap');
const SINK = acc('p9', 'Under-mount sink', { kind: 'product', code: 'SRT-SK1', list_price: 68 });

function renderField(canEdit = true, hostId?: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AccessoryListField kind="product" ownerId="p1" label="Accessories" canEdit={canEdit} ownerHostId={hostId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  service.listOwnerAccessories.mockResolvedValue([TAP, WASTE]);
  service.searchAccessories.mockResolvedValue([TAP, WASTE, TRAP]);
  vi.mocked(getProducts).mockResolvedValue({ data: [] } as never);
});

describe('AccessoryListField', () => {
  it('renders the list in order with spec and a no-picture marker', async () => {
    renderField();
    await screen.findByText('Tap');
    const names = screen.getAllByRole('listitem').map((li) => li.textContent);
    expect(names[0]).toContain('Tap');
    expect(names[0]).toContain('Chrome');
    expect(names[0]).toContain('No picture');
    expect(names[1]).toContain('Waste');
  });

  it('remove saves the remaining ids', async () => {
    service.replaceOwnerAccessories.mockResolvedValue([WASTE]);
    renderField();
    fireEvent.click(await screen.findByLabelText('Remove Tap'));
    await waitFor(() =>
      expect(service.replaceOwnerAccessories).toHaveBeenCalledWith('product', 'p1', [{ accessory_id: 'a2' }]),
    );
  });

  it('has ONE add control and no Box style control (owner 10 Nov)', async () => {
    renderField();
    await screen.findByText('Tap');
    expect(screen.getAllByLabelText(/^Add /)).toHaveLength(1);
    expect(screen.getByLabelText('Add accessory or product to Accessories')).toBeInTheDocument();
    expect(screen.queryByText('Box style')).toBeNull();
    expect(screen.queryByLabelText('Box style')).toBeNull();
  });

  it('the one picker offers library accessories and catalogue products, grouped', async () => {
    vi.mocked(getProducts).mockResolvedValue({
      data: [{ id: 'p7', product_code: 'SRT-TAP', product_name: 'Basin tap' }],
    } as never);
    renderField();
    await screen.findByText('Tap');
    const picker = screen.getByLabelText('Add accessory or product to Accessories');
    await waitFor(() => expect(picker.querySelector('option[value="product:p7"]')).not.toBeNull());
    expect(picker.querySelector('option[value="accessory:a3"]')?.getAttribute('data-group')).toBe('Accessories');
    expect(picker.querySelector('option[value="product:p7"]')?.getAttribute('data-group')).toBe('Products');
    // Already listed ones are not offered again (asked once the list has loaded, as an open picker does).
    const values = (await pickerFetch.current!('', 0)).map((o) => o.value);
    expect(values).toContain('accessory:a3');
    expect(values).not.toContain('accessory:a1');
  });

  it('only the first page carries accessories; later pages are products only', async () => {
    renderField();
    await screen.findByText('Tap');
    await waitFor(() => expect(service.searchAccessories).toHaveBeenCalledTimes(1));
    expect(vi.mocked(getProducts)).toHaveBeenCalledWith(expect.objectContaining({ pageIndex: 0 }));
    const fetchPage = pickerFetch.current!;
    service.searchAccessories.mockClear();
    vi.mocked(getProducts).mockResolvedValue({
      data: [{ id: 'p8', product_code: 'SRT-W', product_name: 'Waste' }],
    } as never);
    const page2 = await fetchPage('', 1);
    expect(service.searchAccessories).not.toHaveBeenCalled();
    expect(page2.map((o) => o.value)).toEqual(['product:p8']);
  });

  it('add saves the list with the picked id appended', async () => {
    service.replaceOwnerAccessories.mockResolvedValue([TAP, WASTE, TRAP]);
    renderField();
    await screen.findByText('Tap');
    const picker = screen.getByLabelText('Add accessory or product to Accessories');
    await waitFor(() => expect(picker.querySelector('option[value="accessory:a3"]')).not.toBeNull());
    fireEvent.change(picker, { target: { value: 'accessory:a3' } });
    await waitFor(() =>
      expect(service.replaceOwnerAccessories).toHaveBeenCalledWith('product', 'p1', [
        { accessory_id: 'a1' },
        { accessory_id: 'a2' },
        { accessory_id: 'a3' },
      ]),
    );
  });

  it('shows a product entry with code and list price, and adds a catalogue product', async () => {
    service.listOwnerAccessories.mockResolvedValue([SINK]);
    vi.mocked(getProducts).mockResolvedValue({
      data: [{ id: 'p7', product_code: 'SRT-TAP', product_name: 'Basin tap' }],
    } as never);
    service.replaceOwnerAccessories.mockResolvedValue([SINK]);
    renderField();
    await screen.findByText('SRT-SK1');
    expect(screen.getByText(/LP: RM/)).toBeInTheDocument();
    const picker = screen.getByLabelText('Add accessory or product to Accessories');
    await waitFor(() => expect(picker.querySelector('option[value="product:p7"]')).not.toBeNull());
    fireEvent.change(picker, { target: { value: 'product:p7' } });
    await waitFor(() =>
      expect(service.replaceOwnerAccessories).toHaveBeenCalledWith('product', 'p1', [
        { product_id: 'p9' },
        { product_id: 'p7' },
      ]),
    );
  });

  it('puts the list back when the save is refused', async () => {
    service.replaceOwnerAccessories.mockRejectedValue(new Error('nope'));
    renderField();
    fireEvent.click(await screen.findByLabelText('Remove Tap'));
    await waitFor(() => expect(service.replaceOwnerAccessories).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByLabelText('Remove Tap')).toBeInTheDocument());
  });

  it('is read-only without edit permission', async () => {
    renderField(false);
    await screen.findByText('Tap');
    expect(screen.queryByLabelText('Remove Tap')).toBeNull();
    expect(screen.queryByLabelText(/^Add /)).toBeNull();
    expect(screen.queryByText('Box style')).toBeNull();
  });

  it('a drag reorder saves the new order', async () => {
    service.replaceOwnerAccessories.mockResolvedValue([WASTE, TAP]);
    renderField();
    await screen.findByText('Tap');
    dnd.onDragEnd?.({ active: { id: 'accessory:a1' }, over: { id: 'accessory:a2' } });
    await waitFor(() =>
      expect(service.replaceOwnerAccessories).toHaveBeenCalledWith('product', 'p1', [
        { accessory_id: 'a2' },
        { accessory_id: 'a1' },
      ]),
    );
  });

  it('does not offer the host product in the add options', async () => {
    service.listOwnerAccessories.mockResolvedValue([]);
    vi.mocked(getProducts).mockResolvedValue({
      data: [
        { id: 'p1', product_code: 'HOST', product_name: 'Host cabinet' },
        { id: 'p7', product_code: 'SRT-TAP', product_name: 'Basin tap' },
      ],
    } as never);
    renderField(true, 'p1');
    const picker = await screen.findByLabelText('Add accessory or product to Accessories');
    await waitFor(() => expect(picker.querySelector('option[value="product:p7"]')).not.toBeNull());
    expect(picker.querySelector('option[value="product:p1"]')).toBeNull();
  });
});
