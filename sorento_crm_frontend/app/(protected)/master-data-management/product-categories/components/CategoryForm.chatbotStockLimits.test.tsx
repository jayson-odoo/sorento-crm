/**
 * AC-SA109 (PLAN-chatbot-stock-ask-v2-24sep.md S1) - `CategoryForm`'s two chatbot
 * stock-limit inputs ("Max quantity (assistant)" / "ETA offset (days)") render only
 * when the caller holds `master_data.chatbot_stock_limits.view`, and are disabled
 * unless the caller also holds `.edit`. No helper text.
 *
 * Tests against the LIVE shape (`useHasPermission`, and `useCategory` returning
 * `chatbot_max_qty` / `chatbot_eta_offset_days` as plain fields on the category
 * object) - NOT `categoryService.ts`'s Phase-1 in-memory overlay, which Phase 2
 * deletes as part of greening this slice.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  });
}

const CAT_ID = '11111111-1111-1111-1111-111111111111';

const permissionState = { view: false, edit: false };
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => {
    if (slug === 'master_data.chatbot_stock_limits.view') return permissionState.view;
    if (slug === 'master_data.chatbot_stock_limits.edit') return permissionState.edit;
    return false;
  },
}));

const useCategoryMock = vi.fn();
const createMutateAsync = vi.fn().mockResolvedValue({});
const updateMutateAsync = vi.fn().mockResolvedValue({});
vi.mock('../hooks/useProductCategories', () => ({
  useCategory: (id: string | null) => useCategoryMock(id),
  useCreateCategory: () => ({ mutateAsync: createMutateAsync, isPending: false }),
  useUpdateCategory: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
}));

vi.mock('@/app/(protected)/project-sales/_shared/components/PriceFloorPanel', () => ({
  PriceFloorPanel: () => <div data-testid="price-floor-stub" />,
}));

import CategoryForm from './CategoryForm';

const LIVE_CATEGORY = {
  id: CAT_ID,
  category_code: 'CAT1',
  category_name: 'Category 1',
  description: '',
  is_active: true,
  is_searchable: true,
  display_order: 0,
  chatbot_max_qty: 50,
  chatbot_eta_offset_days: 7,
};

beforeEach(() => {
  vi.clearAllMocks();
  permissionState.view = false;
  permissionState.edit = false;
  useCategoryMock.mockReturnValue({ data: LIVE_CATEGORY });
});

describe('CategoryForm - chatbot stock-limit fields (AC-SA109)', () => {
  it('hides both inputs without .view', () => {
    permissionState.view = false;
    permissionState.edit = false;

    render(<CategoryForm open onOpenChange={() => {}} categoryId={CAT_ID} />);

    expect(screen.queryByText('Max quantity (assistant)')).not.toBeInTheDocument();
    expect(screen.queryByText('ETA offset (days)')).not.toBeInTheDocument();
  });

  it('shows both inputs, disabled, with .view but not .edit', () => {
    permissionState.view = true;
    permissionState.edit = false;

    render(<CategoryForm open onOpenChange={() => {}} categoryId={CAT_ID} />);

    const maxQtyInput = screen.getByLabelText('Max quantity (assistant)') as HTMLInputElement;
    const etaInput = screen.getByLabelText('ETA offset (days)') as HTMLInputElement;
    expect(maxQtyInput).toBeInTheDocument();
    expect(etaInput).toBeInTheDocument();
    expect(maxQtyInput).toBeDisabled();
    expect(etaInput).toBeDisabled();
  });

  it('shows both inputs, enabled, with .view and .edit', () => {
    permissionState.view = true;
    permissionState.edit = true;

    render(<CategoryForm open onOpenChange={() => {}} categoryId={CAT_ID} />);

    const maxQtyInput = screen.getByLabelText('Max quantity (assistant)') as HTMLInputElement;
    const etaInput = screen.getByLabelText('ETA offset (days)') as HTMLInputElement;
    expect(maxQtyInput).not.toBeDisabled();
    expect(etaInput).not.toBeDisabled();
  });

  it('renders no helper text alongside the two inputs', () => {
    permissionState.view = true;
    permissionState.edit = true;

    render(<CategoryForm open onOpenChange={() => {}} categoryId={CAT_ID} />);

    expect(screen.queryByText(/the highest quantity/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/days added to/i)).not.toBeInTheDocument();
  });
});

/**
 * Blocking 1 (reviewer pass, PR #1221, 85c2e9e7) - a bare
 * `z.union([z.coerce.number(), z.null()])` tries the coerce branch first, and
 * `Number(null)` is `0`, so leaving the two fields empty silently submitted an
 * explicit `0` instead of `null`. R2: unset must stay unset so a category can
 * still opt in later; an explicit `0` is a real value that overrides nothing.
 */
describe('CategoryForm - chatbot stock-limit submit payload (Blocking 1)', () => {
  beforeEach(() => {
    permissionState.view = true;
    permissionState.edit = true;
  });

  it('create: leaving both fields empty submits null, not 0', async () => {
    useCategoryMock.mockReturnValue({ data: undefined });

    render(<CategoryForm open onOpenChange={() => {}} />);

    fireEvent.change(screen.getByLabelText('Category Code *'), { target: { value: 'CAT2' } });
    fireEvent.change(screen.getByLabelText('Category Name *'), { target: { value: 'Category 2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const payload = createMutateAsync.mock.calls[0][0];
    expect(payload.chatbot_max_qty).toBeNull();
    expect(payload.chatbot_eta_offset_days).toBeNull();
  });

  it('create: typing 0 in both fields submits 0, not null', async () => {
    useCategoryMock.mockReturnValue({ data: undefined });

    render(<CategoryForm open onOpenChange={() => {}} />);

    fireEvent.change(screen.getByLabelText('Category Code *'), { target: { value: 'CAT3' } });
    fireEvent.change(screen.getByLabelText('Category Name *'), { target: { value: 'Category 3' } });
    fireEvent.change(screen.getByLabelText('Max quantity (assistant)'), { target: { value: '0' } });
    fireEvent.change(screen.getByLabelText('ETA offset (days)'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const payload = createMutateAsync.mock.calls[0][0];
    expect(payload.chatbot_max_qty).toBe(0);
    expect(payload.chatbot_eta_offset_days).toBe(0);
  });

  it('edit: clearing both fields on a category that had values submits null, not 0', async () => {
    useCategoryMock.mockReturnValue({ data: LIVE_CATEGORY });

    render(<CategoryForm open onOpenChange={() => {}} categoryId={CAT_ID} />);

    fireEvent.change(screen.getByLabelText('Max quantity (assistant)'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('ETA offset (days)'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Update' }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const payload = updateMutateAsync.mock.calls[0][0].data;
    expect(payload.chatbot_max_qty).toBeNull();
    expect(payload.chatbot_eta_offset_days).toBeNull();
  });

  it('edit: saving with the existing values untouched submits them unchanged (0 stays 0)', async () => {
    useCategoryMock.mockReturnValue({
      data: { ...LIVE_CATEGORY, chatbot_max_qty: 0, chatbot_eta_offset_days: 0 },
    });

    render(<CategoryForm open onOpenChange={() => {}} categoryId={CAT_ID} />);
    fireEvent.click(screen.getByRole('button', { name: 'Update' }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const payload = updateMutateAsync.mock.calls[0][0].data;
    expect(payload.chatbot_max_qty).toBe(0);
    expect(payload.chatbot_eta_offset_days).toBe(0);
  });
});
