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
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// The real picker is a Radix popover; a native select stands in for the pick.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    onChange: (v: string) => void;
    fetchOptions: (q: string, p: number) => Promise<{ value: string; label: string }[]>;
    'aria-label'?: string;
  }) => {
    const [opts, setOpts] = React.useState<{ value: string; label: string }[]>([]);
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
          <option key={o.value} value={o.value}>
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

function renderField(canEdit = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AccessoryListField kind="product" ownerId="p1" label="Accessories" canEdit={canEdit} />
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

  it('add saves the list with the picked id appended', async () => {
    service.replaceOwnerAccessories.mockResolvedValue([TAP, WASTE, TRAP]);
    renderField();
    await screen.findByText('Tap');
    const picker = screen.getByLabelText(/Add accessory/);
    await waitFor(() => expect(picker.querySelector('option[value="a3"]')).not.toBeNull());
    fireEvent.change(picker, { target: { value: 'a3' } });
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
    const picker = screen.getByLabelText(/Add product/);
    await waitFor(() => expect(picker.querySelectorAll('option').length).toBe(2));
    fireEvent.change(picker, { target: { value: 'p7' } });
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
    expect(screen.queryByLabelText(/Add accessory/)).toBeNull();
  });
});
