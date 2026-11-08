/**
 * PRICETAG-ACCESSORY-DESIGNER S3: the toolbar "Accessories" button becomes a menu: Default box, then the
 * saved accessories templates (searchable, with the used-in count).
 *
 * Props invented here (the coder must match them), optional on CanvasToolbar:
 *   accessoryTemplates: AccessoryTemplateRecord[]   { id, name, design, used_in, ... } as the API answers
 *   onInsertAccessoryTemplate(template)             called with the picked record
 * "Default box" calls the existing onAddAccessories. Without onInsertAccessoryTemplate the button stays a
 * plain button that calls onAddAccessories (the existing behaviour).
 *
 * Written test-FIRST.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { CanvasToolbar } from './CanvasToolbar';

const noop = () => {};

const TEMPLATES = [
  { id: 't1', name: 'FREE vertical', design: { direction: 'vertical' }, used_in: 2 },
  { id: 't2', name: 'Dealer Kit included', design: { direction: 'horizontal' }, used_in: 1 },
];

function mount(extra: Record<string, unknown> = {}) {
  const onAddAccessories = vi.fn();
  const onInsertAccessoryTemplate = vi.fn();
  render(
    <CanvasToolbar
      tool="select"
      onToolChange={vi.fn()}
      onAddText={noop}
      onAddShape={noop}
      onAddImage={noop}
      onAddProductSlot={noop}
      onAddPriceBadge={noop}
      onAddBadge={noop}
      onAddBarcode={noop}
      onAddProduct={noop}
      onAddSet={noop}
      onAddAlternativesRow={noop}
      onAddAccessories={onAddAccessories}
      onUndo={noop}
      onRedo={noop}
      canUndo={false}
      canRedo={false}
      zoom={1}
      onZoomIn={noop}
      onZoomOut={noop}
      onZoomReset={noop}
      onFit={noop}
      onDeleteSelected={noop}
      onDuplicateSelected={noop}
      onGroupSelected={noop}
      onUngroupSelected={noop}
      hasSelection={false}
      hasMultiSelection={false}
      selectionIsGroup={false}
      accessoryTemplates={TEMPLATES as never}
      onInsertAccessoryTemplate={onInsertAccessoryTemplate}
      {...(extra as object)}
    />,
  );
  return { onAddAccessories, onInsertAccessoryTemplate };
}

async function openMenu() {
  await userEvent.click(screen.getByRole('button', { name: /Accessories/ }));
}

describe('toolbar Accessories menu', () => {
  it('opens a menu with Default box and every saved template by name', async () => {
    mount();
    await openMenu();
    expect(await screen.findByText('Default box')).toBeInTheDocument();
    expect(screen.getByText('FREE vertical')).toBeInTheDocument();
    expect(screen.getByText('Dealer Kit included')).toBeInTheDocument();
  });

  it('Default box adds the default accessories box', async () => {
    const { onAddAccessories, onInsertAccessoryTemplate } = mount();
    await openMenu();
    await userEvent.click(await screen.findByText('Default box'));
    expect(onAddAccessories).toHaveBeenCalledTimes(1);
    expect(onInsertAccessoryTemplate).not.toHaveBeenCalled();
  });

  it('picking a saved template inserts it', async () => {
    const { onAddAccessories, onInsertAccessoryTemplate } = mount();
    await openMenu();
    await userEvent.click(await screen.findByText('FREE vertical'));
    expect(onInsertAccessoryTemplate).toHaveBeenCalledWith(expect.objectContaining({ id: 't1', name: 'FREE vertical' }));
    expect(onAddAccessories).not.toHaveBeenCalled();
  });

  it('shows how many tag templates use each one', async () => {
    mount();
    await openMenu();
    const row = (await screen.findByText('FREE vertical')).closest('[role="menuitem"], [role="option"], li, button')!;
    expect(within(row as HTMLElement).getByText(/2/)).toBeInTheDocument();
  });

  it('the search box narrows the saved templates', async () => {
    mount();
    await openMenu();
    await userEvent.type(await screen.findByPlaceholderText(/Search/i), 'dealer');
    expect(screen.getByText('Dealer Kit included')).toBeInTheDocument();
    expect(screen.queryByText('FREE vertical')).toBeNull();
  });

  it('with no saved templates the menu still offers Default box', async () => {
    mount({ accessoryTemplates: [] });
    await openMenu();
    expect(await screen.findByText('Default box')).toBeInTheDocument();
  });
});
