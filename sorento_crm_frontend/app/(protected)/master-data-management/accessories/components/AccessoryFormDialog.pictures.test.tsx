/**
 * PRICETAG-ACCESSORY-DESIGNER S4: an accessory has several pictures, each with a colour, plus rich Spec
 * lines and a Remark.
 *
 * Plan: PLAN-pricetag-accessory-designer-07nov.md "S4 Master data". Written test-FIRST.
 *
 * Contract assumed: `Accessory.images: { id, attachment_id, url, colour_name, colour_hex }[]` and
 * `Accessory.remark`. The colour of each picture is shown as its name (Black, Grey) wherever it has one.
 * The dialog renders an "Add picture" control on edit. Spec lines and Remark use
 * `components/ui/rich-text-editor` (stood in here by a textarea with data-testid="rte").
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/ui/rich-text-editor', () => {
  const Stand = (props: { value?: string; onChange: (v: string) => void }) => (
    <textarea data-testid="rte" value={props.value ?? ''} onChange={(e) => props.onChange(e.target.value)} />
  );
  return { RichTextEditor: Stand, default: Stand };
});

// The existing mutation hooks are quiet stand-ins; any NEW hook this lane adds stays real (a
// QueryClientProvider is mounted) and talks to the service, which is stubbed below.
vi.mock('../hooks/useAccessories', async (original) => {
  const stub = () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    uploadMutateAsync: vi.fn(),
    deleteMutateAsync: vi.fn(),
    isPending: false,
    busy: false,
  });
  return {
    ...(await original<typeof import('../hooks/useAccessories')>()),
    useCreateAccessory: stub,
    useUpdateAccessory: stub,
    useAccessoryImage: stub,
  };
});
vi.mock('../services/accessoryService', async (original) => ({
  ...(await original<typeof import('../services/accessoryService')>()),
  getAccessories: vi.fn(async () => ({ data: [], pagination: { total: 0, page: 1 } })),
}));

import AccessoryFormDialog from './AccessoryFormDialog';

const IMAGES = [
  { id: 'i1', attachment_id: 'att1', url: 'https://cdn.test/colander-black.jpg', colour_name: 'Black', colour_hex: '#1f2937' },
  { id: 'i2', attachment_id: 'att2', url: 'https://cdn.test/colander-grey.jpg', colour_name: 'Grey', colour_hex: '#9ca3af' },
];

const ACCESSORY = {
  id: 'a1',
  name: 'COLANDER',
  spec: '390x200x140',
  remark: 'Colour follows sink',
  image: { attachment_id: 'att1', url: IMAGES[0].url },
  images: IMAGES,
  product_count: 0,
  combo_count: 0,
};

function mount(accessory: unknown = ACCESSORY, canEdit = true) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AccessoryFormDialog open onOpenChange={vi.fn()} accessory={accessory as never} canEdit={canEdit} />
    </QueryClientProvider>,
  );
}

describe('AccessoryFormDialog pictures', () => {
  it('shows both pictures of an accessory (a picture carries no colour label any more, S7)', () => {
    mount();
    const dialog = screen.getByRole('dialog');
    const sources = Array.from(dialog.querySelectorAll('img')).map((i) => i.getAttribute('src'));
    expect(sources).toEqual(expect.arrayContaining([IMAGES[0].url, IMAGES[1].url]));
    expect(within(dialog).queryByText('Black')).toBeNull();
    expect(within(dialog).queryByText('Grey')).toBeNull();
  });

  it('offers Add picture', () => {
    mount();
    expect(screen.getByRole('button', { name: /Add picture/ })).toBeInTheDocument();
  });

  it('can reorder the pictures (a drag handle per picture)', () => {
    mount();
    expect(screen.getAllByRole('button', { name: /Reorder picture/ })).toHaveLength(2);
  });

  it('has a Remark field and Spec lines, both rich text', () => {
    mount();
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Spec lines')).toBeInTheDocument();
    expect(within(dialog).getByText('Remark')).toBeInTheDocument();
    expect(within(dialog).getAllByTestId('rte').length).toBeGreaterThanOrEqual(2);
  });

  it('prefills spec and remark', () => {
    mount();
    const values = screen.getAllByTestId('rte').map((el) => (el as HTMLTextAreaElement).value);
    expect(values).toEqual(expect.arrayContaining(['390x200x140', 'Colour follows sink']));
  });

  it('a new accessory has no pictures yet (they need the record) but still has Spec lines and Remark', () => {
    mount(null);
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).queryByRole('button', { name: /Add picture/ })).toBeNull();
    expect(within(dialog).getAllByTestId('rte').length).toBeGreaterThanOrEqual(2);
  });
});
