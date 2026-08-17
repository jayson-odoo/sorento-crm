/**
 * The floor panel embedded in the product Pricing tab and the category editor.
 *
 * The case worth pinning hardest is INHERITANCE: a product with no rule of its own is
 * still governed by a floor, and a panel that showed "none set" there would be a lie by
 * omission. Everything else follows from that - the source line, and the fact that
 * "Clear" is only offered when there is something of this target's own to clear.
 *
 * Clearing deletes a rule, so it goes through the shared confirmation dialog. A one-click
 * clear would silently move a product onto a different policy.
 */
import React, { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EffectivePriceFloor } from '../types/project.types';

const getEffectivePriceFloor = vi.fn();
const deletePriceFloor = vi.fn();

vi.mock('../services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/projectService')>();
  return {
    ...actual,
    getEffectivePriceFloor: (...args: unknown[]) => getEffectivePriceFloor(...args),
    deletePriceFloor: (...args: unknown[]) => deletePriceFloor(...args),
  };
});

// The dialog is exercised by its own surface (the pricing policy screen). Here we only
// care THAT opening it hands over the locked target, not how it renders.
const dialogProps: unknown[] = [];
vi.mock('./PriceFloorDialog', () => ({
  PriceFloorDialog: (props: Record<string, unknown>) => {
    dialogProps.push(props);
    return <div data-testid="floor-dialog">{String(props.lockedTarget)}</div>;
  },
}));

import { PriceFloorPanel } from './PriceFloorPanel';

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryWrapper';
  return Wrapper;
}

function view(overrides: Partial<EffectivePriceFloor> = {}): EffectivePriceFloor {
  return {
    target_level: 'product',
    target_id: 'p-1',
    target_label: 'BASIN-001',
    list_price: '1000.00',
    own_rule: null,
    effective: null,
    ...overrides,
  };
}

const PRODUCT = { level: 'product' as const, id: 'p-1', label: 'BASIN-001' };

beforeEach(() => {
  getEffectivePriceFloor.mockReset();
  deletePriceFloor.mockReset();
  dialogProps.length = 0;
});

describe('PriceFloorPanel', () => {
  it('shows a skeleton while the floor is being read', () => {
    getEffectivePriceFloor.mockReturnValue(new Promise(() => {}));

    render(<PriceFloorPanel target={PRODUCT} />, { wrapper: wrapper() });

    expect(screen.getByTestId('price-floor-loading')).toBeTruthy();
  });

  it('tells a product with no rule of its own which floor it INHERITS, and from where', async () => {
    getEffectivePriceFloor.mockResolvedValue(
      view({
        effective: {
          rule_id: 'r-1',
          level: 'category',
          mode: 'percent',
          value: '80.00',
          amount: '800.00',
          source_label: 'Basins',
        },
      }),
    );

    render(<PriceFloorPanel target={PRODUCT} />, { wrapper: wrapper() });

    expect(
      await screen.findByText('At least 80% of the list price (RM 800.00)'),
    ).toBeTruthy();
    expect(screen.getByText('Inherited from the Basins category')).toBeTruthy();
    // Nothing of its own to clear, so clearing is not offered.
    expect(screen.queryByText(/Clear this product/)).toBeNull();
    expect(screen.getByText('Set a floor for this product')).toBeTruthy();
  });

  it('offers to change and to clear once the product carries its own rule', async () => {
    getEffectivePriceFloor.mockResolvedValue(
      view({
        own_rule: {
          id: 'r-own',
          product_id: 'p-1',
          product_code: 'BASIN-001',
          mode: 'absolute',
          value: '950.00',
          is_active: true,
          level: 'product',
        },
        effective: {
          rule_id: 'r-own',
          level: 'product',
          mode: 'absolute',
          value: '950.00',
          amount: '950.00',
          source_label: 'BASIN-001',
        },
      }),
    );

    render(<PriceFloorPanel target={PRODUCT} />, { wrapper: wrapper() });

    expect(await screen.findByText('Set on this product')).toBeTruthy();
    expect(screen.getByText(/Change this product/)).toBeTruthy();
    expect(screen.getByText(/Clear this product/)).toBeTruthy();
  });

  it('states plainly when no floor reaches this product at all', async () => {
    getEffectivePriceFloor.mockResolvedValue(view());

    render(<PriceFloorPanel target={PRODUCT} />, { wrapper: wrapper() });

    expect(
      await screen.findByText(
        /No floor applies to this product. Any quoted price is accepted without an alert./,
      ),
    ).toBeTruthy();
  });

  it('says why a rule the product owns is not the one in force when it is switched off', async () => {
    getEffectivePriceFloor.mockResolvedValue(
      view({
        own_rule: {
          id: 'r-own',
          product_id: 'p-1',
          mode: 'percent',
          value: '95.00',
          is_active: false,
          level: 'product',
        },
        effective: {
          rule_id: 'r-cat',
          level: 'category',
          mode: 'percent',
          value: '80.00',
          amount: '800.00',
          source_label: 'Basins',
        },
      }),
    );

    render(<PriceFloorPanel target={PRODUCT} />, { wrapper: wrapper() });

    expect(await screen.findByText('Switched off')).toBeTruthy();
    expect(
      screen.getByText(/has a floor of its own, but it is switched off/),
    ).toBeTruthy();
  });

  it('surfaces the failure and offers a retry rather than an empty panel', async () => {
    getEffectivePriceFloor.mockRejectedValue(
      new Error('Permission required: projects.types.view'),
    );

    render(<PriceFloorPanel target={PRODUCT} />, { wrapper: wrapper() });

    expect(
      await screen.findByText('Permission required: projects.types.view'),
    ).toBeTruthy();
    expect(screen.getByText('Try again')).toBeTruthy();
  });

  it('asks nothing of the server until the record it belongs to exists', () => {
    render(
      <PriceFloorPanel
        target={null}
        disabledReason="Save the product first, then set its floor here."
      />,
      { wrapper: wrapper() },
    );

    expect(
      screen.getByText('Save the product first, then set its floor here.'),
    ).toBeTruthy();
    expect(getEffectivePriceFloor).not.toHaveBeenCalled();
  });

  it('hands the dialog a target that is already decided, named not id-ed', async () => {
    getEffectivePriceFloor.mockResolvedValue(view());

    render(<PriceFloorPanel target={PRODUCT} />, { wrapper: wrapper() });

    fireEvent.click(await screen.findByText('Set a floor for this product'));

    await waitFor(() => expect(dialogProps.length).toBeGreaterThan(0));
    const props = dialogProps[0] as Record<string, unknown>;
    expect(props.lockedTarget).toEqual({
      level: 'product',
      id: 'p-1',
      label: 'BASIN-001',
    });
  });

  it('confirms before clearing, because that moves the product onto a different policy', async () => {
    getEffectivePriceFloor.mockResolvedValue(
      view({
        own_rule: {
          id: 'r-own',
          product_id: 'p-1',
          mode: 'absolute',
          value: '950.00',
          is_active: true,
          level: 'product',
        },
        effective: {
          rule_id: 'r-own',
          level: 'product',
          mode: 'absolute',
          value: '950.00',
          amount: '950.00',
          source_label: 'BASIN-001',
        },
      }),
    );
    deletePriceFloor.mockResolvedValue(undefined);

    render(<PriceFloorPanel target={PRODUCT} />, { wrapper: wrapper() });

    fireEvent.click(await screen.findByText(/Clear this product/));

    expect(await screen.findByText('Confirm delete')).toBeTruthy();
    expect(screen.getByText(/This action cannot be undone/)).toBeTruthy();
    // Not deleted yet: the dialog is the gate, not a formality.
    expect(deletePriceFloor).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(deletePriceFloor).toHaveBeenCalledWith('r-own'));
  });

  it('reads the floor for a CATEGORY with the same panel', async () => {
    getEffectivePriceFloor.mockResolvedValue(
      view({
        target_level: 'category',
        target_id: 'c-1',
        target_label: 'Basins',
        list_price: null,
        effective: {
          rule_id: 'r-anc',
          level: 'category_ancestor',
          mode: 'percent',
          value: '70.00',
          // No list price on a category, so no ringgit amount to state.
          amount: null,
          source_label: 'Sanitary Ware',
        },
      }),
    );

    render(
      <PriceFloorPanel target={{ level: 'category', id: 'c-1', label: 'Basins' }} />,
      { wrapper: wrapper() },
    );

    expect(await screen.findByText('At least 70% of the list price')).toBeTruthy();
    expect(screen.getByText('Inherited from the Sanitary Ware category')).toBeTruthy();
    expect(screen.getByText('Set a floor for this category')).toBeTruthy();
  });
});
