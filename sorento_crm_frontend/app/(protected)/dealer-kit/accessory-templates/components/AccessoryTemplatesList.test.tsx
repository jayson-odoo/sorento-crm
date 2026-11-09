/**
 * PRICETAG-ACCESSORY-DESIGNER S5: the management page list at /dealer-kit/accessory-templates.
 *
 * Plan: PLAN-pricetag-accessory-designer-07nov.md "S5 Management page"; copied from tag-sizes. Written
 * test-FIRST: `./AccessoryTemplatesList` does not exist yet.
 *
 * Invented names (the coder must match them):
 *   component  export { AccessoryTemplatesList } from './AccessoryTemplatesList'
 *   hooks      ../hooks/useAccessoryTemplates exports
 *                useAccessoryTemplatesQuery()            -> { data: AccessoryTemplateRecord[], isLoading, error, refetch }
 *                useUpdateAccessoryTemplate()            -> mutation, called mutateAsync({ id, input: { name } })
 *                useDeleteAccessoryTemplate()            -> { run({ id, subject }) }  (deferred action)
 *                useAccessoryTemplateUsage(id, enabled)  -> { data: { templates: { id, name }[] } }
 *   row menu   a button whose name matches /actions/i, items "Rename template" and "Delete template"
 *   rename     dialog with a "Name" input and a "Save" button
 *   used in    the count is a button; clicking it lists the tag template names
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));
vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  return {
    Stage: passthrough('stage'),
    Layer: passthrough('layer'),
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Text: passthrough('text'),
    Path: passthrough('path'),
    Image: passthrough('image'),
    Ellipse: passthrough('ellipse'),
    Line: passthrough('line'),
    Circle: passthrough('circle'),
  };
});

const ROWS = vi.hoisted(() => [
  {
    id: 't1',
    name: 'FREE vertical',
    design: { direction: 'vertical', headerText: 'FREE', card: { width_mm: 30, height_mm: 20, elements: [] } },
    used_in: 2,
    created_by_name: 'Aisyah',
    created_at: '2026-11-05T02:00:00',
    updated_at: '2026-11-07T10:30:00',
  },
  {
    id: 't2',
    name: 'Dealer Kit included',
    design: { direction: 'horizontal' },
    used_in: 0,
    created_by_name: null,
    created_at: '2026-10-01T02:00:00',
    updated_at: '2026-10-02T03:00:00',
  },
]);
const hooks = vi.hoisted(() => ({
  update: vi.fn(),
  run: vi.fn(),
}));
vi.mock('../hooks/useAccessoryTemplates', () => ({
  useAccessoryTemplatesQuery: () => ({ data: ROWS, isLoading: false, error: null, refetch: vi.fn() }),
  useUpdateAccessoryTemplate: () => ({ mutateAsync: hooks.update, mutate: hooks.update, isPending: false }),
  useDeleteAccessoryTemplate: () => ({ run: hooks.run }),
  useAccessoryTemplateUsage: () => ({
    data: { templates: [{ id: 'x1', name: 'Kitchen sinks A5' }, { id: 'x2', name: 'Wash basins A6' }] },
    isLoading: false,
  }),
}));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: hooks.run, targetId: null, isPending: false, countdown: null }),
  useRowPending: () => () => false,
}));

import { AccessoryTemplatesList } from './AccessoryTemplatesList';

function mount() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AccessoryTemplatesList />
    </QueryClientProvider>,
  );
}

describe('AccessoryTemplatesList', () => {
  it('renders a grid with the Preview, Name, Used in, Updated and By columns', () => {
    mount();
    for (const header of ['Preview', 'Name', 'Used in', 'Updated', 'By']) {
      expect(screen.getByRole('columnheader', { name: new RegExp(`^${header}`) })).toBeInTheDocument();
    }
  });

  it('one row per template with its name, creator and used-in count', () => {
    mount();
    expect(screen.getByText('FREE vertical')).toBeInTheDocument();
    expect(screen.getByText('Dealer Kit included')).toBeInTheDocument();
    expect(screen.getByText('Aisyah')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /2 tag templates/ })).toBeInTheDocument();
  });

  it('shows the updated date as dd/mm/yyyy', () => {
    mount();
    expect(screen.getByText('07/11/2026')).toBeInTheDocument();
    expect(screen.getByText('02/10/2026')).toBeInTheDocument();
  });

  it('clicking the used-in count lists the tag templates by name', async () => {
    mount();
    await userEvent.click(screen.getByRole('button', { name: /2 tag templates/ }));
    expect(await screen.findByText('Kitchen sinks A5')).toBeInTheDocument();
    expect(screen.getByText('Wash basins A6')).toBeInTheDocument();
  });

  it('Rename opens a dialog and saves the new name', async () => {
    mount();
    await userEvent.click(screen.getAllByRole('button', { name: /actions/i })[0]);
    await userEvent.click(await screen.findByText('Rename template'));
    const dialog = await screen.findByRole('dialog');
    const input = within(dialog).getByLabelText('Name');
    expect(input).toHaveValue('FREE vertical');
    await userEvent.clear(input);
    await userEvent.type(input, 'FREE tall');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(hooks.update).toHaveBeenCalledWith({ id: 't1', input: { name: 'FREE tall' } }),
    );
  });

  it('Delete parks a deferred action on the row instead of deleting at once', async () => {
    mount();
    await userEvent.click(screen.getAllByRole('button', { name: /actions/i })[0]);
    await userEvent.click(await screen.findByText('Delete template'));
    expect(hooks.run).toHaveBeenCalledWith({ id: 't1', subject: 'FREE vertical' });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('has no Add button: the design is made in the Tag Template designer', () => {
    mount();
    expect(screen.queryByRole('button', { name: /^Add/ })).toBeNull();
  });
});
