/**
 * PRICETAG-ACCESSORY-DESIGNER S7: the accessory dialog shows Pictures and Colours as two separate sections.
 * A picture carries no colour select any more; Save sends the colours list through the accessories service's
 * `replaceAccessoryColours(id, colours)` (invented name, `colours` = [{ name, hex }] in order).
 * Written test-FIRST.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const svc = vi.hoisted(() => ({ replaceAccessoryColours: vi.fn(), updateFn: vi.fn() }));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/ui/rich-text-editor', () => {
  const Stand = (props: { value?: string; onChange: (v: string) => void }) => (
    <textarea data-testid="rte" value={props.value ?? ''} onChange={(e) => props.onChange(e.target.value)} />
  );
  return { RichTextEditor: Stand, default: Stand };
});
vi.mock('../services/accessoryService', async (original) => ({
  ...(await original<typeof import('../services/accessoryService')>()),
  replaceAccessoryColours: svc.replaceAccessoryColours,
}));
vi.mock('../hooks/useAccessories', async (original) => {
  const quiet = () => ({
    mutate: vi.fn(), mutateAsync: vi.fn(), uploadMutateAsync: vi.fn(), deleteMutateAsync: vi.fn(),
    addMutateAsync: vi.fn(), patchMutateAsync: vi.fn(), orderMutateAsync: vi.fn(), isPending: false, busy: false,
  });
  return {
    ...(await original<typeof import('../hooks/useAccessories')>()),
    useCreateAccessory: () => ({ ...quiet(), mutateAsync: vi.fn() }),
    useUpdateAccessory: () => ({ ...quiet(), mutateAsync: svc.updateFn }),
    useAccessoryImage: quiet,
    useAccessoryPictures: quiet,
  };
});

import AccessoryFormDialog from './AccessoryFormDialog';

const PICTURES = [
  { id: 'i1', attachment_id: 'att1', url: 'https://cdn.test/a.jpg', colour_name: null, colour_hex: null },
];
const ACCESSORY = {
  id: 'a1',
  name: 'COLANDER',
  spec: '390x200x140',
  remark: null,
  image: { attachment_id: 'att1', url: PICTURES[0].url },
  images: PICTURES,
  colours: [
    { id: 'c1', name: 'Black', hex: '#1f2937' },
    { id: 'c2', name: 'Grey', hex: '#9ca3af' },
  ],
  product_count: 0,
  combo_count: 0,
};

function mount(accessory: unknown = ACCESSORY) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AccessoryFormDialog open onOpenChange={vi.fn()} accessory={accessory as never} canEdit />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  svc.updateFn.mockResolvedValue({});
  svc.replaceAccessoryColours.mockResolvedValue([]);
});

describe('AccessoryFormDialog pictures and colours', () => {
  it('shows Pictures and Colours as separate sections', () => {
    mount();
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Pictures')).toBeInTheDocument();
    expect(within(dialog).getByText('Colours')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Colour name 1')).toHaveValue('Black');
    expect(within(dialog).getByLabelText('Colour name 2')).toHaveValue('Grey');
  });

  it('one picture can sit beside two colours', () => {
    mount();
    const dialog = screen.getByRole('dialog');
    expect(dialog.querySelectorAll('img[src="https://cdn.test/a.jpg"]').length).toBeGreaterThanOrEqual(1);
    expect(within(dialog).getAllByLabelText(/^Colour name/)).toHaveLength(2);
  });

  it('Escape in an open colour picker closes only the picker, not the dialog or its rows', async () => {
    const onOpenChange = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AccessoryFormDialog open onOpenChange={onOpenChange} accessory={ACCESSORY as never} canEdit />
      </QueryClientProvider>,
    );
    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getAllByTitle('#1f2937')[0]);
    const hue = await screen.findByRole('slider', { name: 'Hue' });
    // Focus is still on the swatch that opened it (the browser case), not inside the popover.
    fireEvent.keyDown(within(dialog).getAllByTitle('#1f2937')[0], { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('slider', { name: 'Hue' })).toBeNull());
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('Colour name 1')).toHaveValue('Black');
  });

  it('a colour row wraps on narrow screens: the name input takes a full line', () => {
    mount();
    const name = screen.getByLabelText('Colour name 1');
    expect(name.className).toMatch(/basis-full/);
    expect(name.className).toMatch(/sm:basis-0|sm:flex-1/);
  });

  it('a picture has no colour select', () => {
    mount();
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).queryByLabelText(/^Colour of picture/)).toBeNull();
    expect(within(dialog).queryByText('No colour')).toBeNull();
    expect(within(dialog).queryByRole('option', { name: 'Gunmetal' })).toBeNull();
  });

  it('Save sends the colours through replaceAccessoryColours', async () => {
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(svc.replaceAccessoryColours).toHaveBeenCalledWith('a1', [
        { name: 'Black', hex: '#1f2937' },
        { name: 'Grey', hex: '#9ca3af' },
      ]),
    );
  });

  it('removing a colour and saving sends the shorter list', async () => {
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Remove colour 1' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(svc.replaceAccessoryColours).toHaveBeenCalledWith('a1', [{ name: 'Grey', hex: '#9ca3af' }]),
    );
  });

  it('adding a colour and saving sends it last', async () => {
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Add colour' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(svc.replaceAccessoryColours).toHaveBeenCalled());
    const sent = svc.replaceAccessoryColours.mock.calls[0][1] as { hex: string }[];
    expect(sent).toHaveLength(3);
    expect(sent[2].hex).toBe('#1f2937');
  });

  it('an accessory with no colours saves an empty list', async () => {
    mount({ ...ACCESSORY, colours: [] });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(svc.replaceAccessoryColours).toHaveBeenCalledWith('a1', []));
  });
});
