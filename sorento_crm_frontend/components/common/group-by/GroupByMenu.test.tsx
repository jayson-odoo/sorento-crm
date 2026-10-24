/**
 * STOCK-GROUPBY S1 (red): the Group by bar. Contract `PLAN-stock-groupby-18oct.md` 5.2,
 * UAC AC-15, AC-16.
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { GroupByMenu } from './GroupByMenu';

const OPTIONS = [
  { id: 'location', label: 'Location' },
  { id: 'customer', label: 'Customer' },
  { id: 'project', label: 'Project' },
  { id: 'agent', label: 'Agent' },
  { id: 'supplier', label: 'Supplier' },
  { id: 'type', label: 'Type' },
];

function setup(value: string[], extra: Partial<React.ComponentProps<typeof GroupByMenu>> = {}) {
  const onChange = vi.fn();
  const utils = render(
    <GroupByMenu options={OPTIONS} value={value} defaultValue={['location']} onChange={onChange} {...extra} />,
  );
  return { onChange, ...utils };
}

function openMenu() {
  fireEvent.pointerDown(screen.getByTestId('group-by-trigger'), { button: 0 });
}

describe('GroupByMenu (AC-15, AC-16)', () => {
  it('AC-15 the bar holds the Group by button, and Expand all / Collapse all only when handlers are given', () => {
    const { unmount } = setup(['location']);
    expect(screen.getByTestId('group-by-bar')).toBeInTheDocument();
    expect(screen.getByTestId('group-by-trigger')).toHaveTextContent('Group by');
    expect(screen.queryByTestId('group-by-expand-all')).not.toBeInTheDocument();
    expect(screen.queryByTestId('group-by-collapse-all')).not.toBeInTheDocument();
    unmount();
    const onExpandAll = vi.fn();
    const onCollapseAll = vi.fn();
    setup(['location'], { onExpandAll, onCollapseAll });
    fireEvent.click(screen.getByTestId('group-by-expand-all'));
    fireEvent.click(screen.getByTestId('group-by-collapse-all'));
    expect(screen.getByTestId('group-by-expand-all')).toHaveTextContent('Expand all');
    expect(screen.getByTestId('group-by-collapse-all')).toHaveTextContent('Collapse all');
    expect(onExpandAll).toHaveBeenCalledTimes(1);
    expect(onCollapseAll).toHaveBeenCalledTimes(1);
  });

  it('AC-15 the menu holds six checkbox items in the order Location, Customer, Project, Agent, Supplier, Type', async () => {
    setup(['location']);
    openMenu();
    const items = await screen.findAllByRole('menuitemcheckbox');
    expect(items.map((el) => el.getAttribute('data-testid'))).toEqual(
      OPTIONS.map((o) => `group-by-option-${o.id}`),
    );
    expect(items.map((el) => (el.textContent ?? '').replace(/\d+$/, '').trim())).toEqual(
      OPTIONS.map((o) => o.label),
    );
  });

  it('AC-15 ticked items are aria-checked and show their level number in order', async () => {
    setup(['customer', 'location', 'type']);
    openMenu();
    await screen.findAllByRole('menuitemcheckbox');
    expect(screen.getByTestId('group-by-option-customer')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('group-by-option-location')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('group-by-option-type')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('group-by-option-project')).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByTestId('group-by-level-customer')).toHaveTextContent('1');
    expect(screen.getByTestId('group-by-level-location')).toHaveTextContent('2');
    expect(screen.getByTestId('group-by-level-type')).toHaveTextContent('3');
    expect(screen.queryByTestId('group-by-level-project')).not.toBeInTheDocument();
  });

  it('AC-16 clicking an unticked item adds it as the last level', async () => {
    const { onChange } = setup(['location', 'customer']);
    openMenu();
    fireEvent.click(await screen.findByTestId('group-by-option-project'));
    expect(onChange).toHaveBeenCalledWith(['location', 'customer', 'project']);
  });

  it('AC-16 clicking a ticked item removes it and later levels move up', async () => {
    const { onChange } = setup(['location', 'customer', 'project']);
    openMenu();
    fireEvent.click(await screen.findByTestId('group-by-option-customer'));
    expect(onChange).toHaveBeenCalledWith(['location', 'project']);
  });

  it('AC-16 the last level can be removed, leaving none', async () => {
    const { onChange } = setup(['location']);
    openMenu();
    fireEvent.click(await screen.findByTestId('group-by-option-location'));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it('AC-16 the menu stays open after a click', async () => {
    const { onChange } = setup(['location']);
    openMenu();
    fireEvent.click(await screen.findByTestId('group-by-option-agent'));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('group-by-option-supplier')).toBeInTheDocument();
  });

  it('AC-16 the chip reads Group by and the labels joined by " > ", with an x that resets', () => {
    const { onChange } = setup(['location', 'customer', 'project']);
    const chip = screen.getByTestId('group-by-chip');
    expect(chip).toHaveTextContent('Group by');
    expect(chip).toHaveTextContent('Location > Customer > Project');
    const clear = screen.getByTestId('group-by-chip-clear');
    expect(clear).toHaveAttribute('aria-label', 'Reset group by');
    fireEvent.click(clear);
    expect(onChange).toHaveBeenCalledWith(['location']);
  });

  it('AC-16 with Location alone (the default) the chip has no x', () => {
    setup(['location']);
    expect(screen.getByTestId('group-by-chip')).toHaveTextContent('Location');
    expect(screen.queryByTestId('group-by-chip-clear')).not.toBeInTheDocument();
  });

  it('AC-16 with no levels the chip reads "Group by: none" and offers the x', () => {
    const { onChange } = setup([]);
    const chip = screen.getByTestId('group-by-chip');
    expect(chip.textContent?.replace(/\s+/g, ' ').trim()).toMatch(/Group by:? none/);
    expect(within(chip).queryByText('Location')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('group-by-chip-clear'));
    expect(onChange).toHaveBeenCalledWith(['location']);
  });

  it('AC-16 a different level list than the default shows the x even for one level', () => {
    setup(['customer']);
    expect(screen.getByTestId('group-by-chip')).toHaveTextContent('Customer');
    expect(screen.getByTestId('group-by-chip-clear')).toBeInTheDocument();
  });
});
