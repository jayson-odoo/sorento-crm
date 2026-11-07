/**
 * PRICETAG-ACCESSORY-DESIGNER S6: the "Box style" picker on a product's and a combo's "Accessories
 * included" section (AccessoryListField). Plan: "Box style override per product / per combo".
 * Written test-FIRST.
 *
 * Invented names (the coder must match them):
 *  - the owner's `box_style_id` comes with the list the field already loads (one GET): the list array
 *    carries it as a `box_style_id` property (`listOwnerAccessories` -> OwnerAccessories)
 *  - accessoryService.replaceOwnerAccessories(kind, id, items, boxStyleId?)  4th argument: a template id
 *    to set, null to clear, left out (exactly 3 arguments) when only the list changed
 *  - saved templates come from `listAccessoryTemplates()` in
 *    `app/(protected)/dealer-kit/services/accessoryTemplateService`
 *  - the picker is a SearchableSelect with aria-label "Box style", `clearable`, placeholder
 *    "Tag template's own box", options { value: template id, label: template name }
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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
vi.mock('../../services/productService', () => ({ getProducts: vi.fn(async () => ({ data: [] })) }));
vi.mock('@/app/(protected)/dealer-kit/services/accessoryTemplateService', () => ({
  listAccessoryTemplates: vi.fn(async () => [
    { id: 't1', name: 'FREE vertical', design: {}, used_in: 2 },
    { id: 't2', name: 'Row of three', design: {}, used_in: 0 },
  ]),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/ui/rich-text-editor', () => ({ RichTextEditor: () => null, default: () => null }));
// A native select stands in for the Radix picker; it exposes what the picker was given.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value?: string | null;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    fetchOptions?: (q: string, p: number) => Promise<{ value: string; label: string }[]>;
    placeholder?: string;
    clearable?: boolean;
    'aria-label'?: string;
  }) => {
    const [fetched, setFetched] = React.useState<{ value: string; label: string }[]>([]);
    React.useEffect(() => {
      void props.fetchOptions?.('', 0).then(setFetched);
    }, []);
    const opts = props.options ?? fetched;
    return (
      <select
        aria-label={props['aria-label']}
        data-clearable={String(Boolean(props.clearable))}
        value={props.value ?? ''}
        onChange={(e) => props.onChange(e.target.value)}
      >
        <option value="">{props.placeholder ?? ''}</option>
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

const BOARD = {
  kind: 'accessory', code: null, list_price: null, id: 'a1', name: 'CHOPPING BOARD', spec: null, remark: null,
  image: null, images: [], entry: { image_id: null, name: null, spec: null, remark: null },
  product_count: 0, combo_count: 0,
} as unknown as AccessoryEntry;

const withStyle = (id: string | null) => Object.assign([BOARD], { box_style_id: id });

function mount(kind: 'product' | 'combo' = 'product', canEdit = true) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AccessoryListField kind={kind} ownerId="o1" label="Accessories included" canEdit={canEdit} />
    </QueryClientProvider>,
  );
}

const picker = () => screen.findByLabelText('Box style') as Promise<HTMLSelectElement>;

beforeEach(() => {
  vi.clearAllMocks();
  service.listOwnerAccessories.mockResolvedValue(withStyle(null));
  service.replaceOwnerAccessories.mockResolvedValue([BOARD]);
  service.searchAccessories.mockResolvedValue([]);
});

describe.each(['product', 'combo'] as const)('Box style picker on a %s', (kind) => {
  it('shows a "Box style" select, clearable, whose empty option is the tag template\'s own box', async () => {
    mount(kind);
    const select = await picker();
    expect(select.getAttribute('data-clearable')).toBe('true');
    const options = Array.from(select.querySelectorAll('option'));
    expect(options[0].value).toBe('');
    expect(options[0].textContent).toBe("Tag template's own box");
  });

  it('lists the saved accessories templates by name', async () => {
    mount(kind);
    const select = await picker();
    await waitFor(() => expect(select.querySelectorAll('option').length).toBe(3));
    expect(Array.from(select.querySelectorAll('option')).map((o) => o.textContent)).toEqual([
      "Tag template's own box",
      'FREE vertical',
      'Row of three',
    ]);
  });

  it('starts on the style the owner already names', async () => {
    service.listOwnerAccessories.mockResolvedValue(withStyle('t2'));
    mount(kind);
    const select = await picker();
    await waitFor(() => expect(select.value).toBe('t2'));
  });

  it('choosing one saves box_style_id through the list PUT, with the current list', async () => {
    mount(kind);
    const select = await picker();
    await waitFor(() => expect(select.querySelector('option[value="t1"]')).not.toBeNull());
    fireEvent.change(select, { target: { value: 't1' } });
    await waitFor(() =>
      expect(service.replaceOwnerAccessories).toHaveBeenCalledWith(kind, 'o1', [{ accessory_id: 'a1' }], 't1'),
    );
  });

  it('clearing it sends null', async () => {
    service.listOwnerAccessories.mockResolvedValue(withStyle('t1'));
    mount(kind);
    const select = await picker();
    await waitFor(() => expect(select.value).toBe('t1'));
    fireEvent.change(select, { target: { value: '' } });
    await waitFor(() =>
      expect(service.replaceOwnerAccessories).toHaveBeenCalledWith(kind, 'o1', [{ accessory_id: 'a1' }], null),
    );
  });
});

describe('Box style picker, other rules', () => {
  it('a view-only reader sees the chosen style read-only, by name', async () => {
    service.listOwnerAccessories.mockResolvedValue(withStyle('t2'));
    mount('product', false);
    await screen.findByText('CHOPPING BOARD');
    expect(screen.getByText('Box style')).toBeInTheDocument();
    expect(await screen.findByText('Row of three')).toBeInTheDocument();
    expect(screen.queryByLabelText('Box style')).toBeNull();
  });

  it('a view-only reader of an owner with no style sees the tag template\'s own box', async () => {
    mount('product', false);
    await screen.findByText('CHOPPING BOARD');
    expect(screen.getByText("Tag template's own box")).toBeInTheDocument();
  });

  it('a list change alone leaves the style out of the PUT', async () => {
    mount('product');
    fireEvent.click(await screen.findByLabelText('Remove CHOPPING BOARD'));
    await waitFor(() => expect(service.replaceOwnerAccessories).toHaveBeenCalled());
    expect(service.replaceOwnerAccessories.mock.calls[0]).toEqual(['product', 'o1', []]);
  });

  it('read-only readers do not get the picker', async () => {
    const view = mount('product', false);
    await screen.findByText('CHOPPING BOARD');
    expect(screen.queryByLabelText('Box style')).toBeNull();
    view.unmount();
    mount('product', true);
    expect(await picker()).toBeInTheDocument();
  });
});
