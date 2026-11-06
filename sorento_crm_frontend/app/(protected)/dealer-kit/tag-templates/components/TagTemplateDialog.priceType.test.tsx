/**
 * PRICETAG-COMBO-FORMAT AC-28: the new-template dialog has a "Price type" toggle group (LP, SP,
 * LP & SP) beside Family, unset allowed, and saving sends `price_type`.
 *
 * Written test-FIRST. The dialog has no such control. The three options are located by their
 * visible text, so the test holds for a ToggleGroup of radios or of buttons.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({ SearchableSelect: () => null }));

const createTemplate = vi.fn();
vi.mock('../../services/tagTemplateService', () => ({
  createTemplate: (...a: unknown[]) => createTemplate(...a),
}));

import { TagTemplateDialog } from './TagTemplateDialog';

function open() {
  render(<TagTemplateDialog open onOpenChange={vi.fn()} />);
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Bathroom Furniture SP' } });
}

const option = (label: string) => screen.getByText(new RegExp(`^${label.replace('&', '\\&')}$`));

async function save() {
  fireEvent.click(screen.getByRole('button', { name: /create template/i }));
  await waitFor(() => expect(createTemplate).toHaveBeenCalled());
  return createTemplate.mock.calls[0][0] as Record<string, unknown>;
}

beforeEach(() => {
  createTemplate.mockReset();
  createTemplate.mockResolvedValue({ id: 't1', name: 'Bathroom Furniture SP' });
});

describe('TagTemplateDialog price type (AC-28)', () => {
  it('AC-28: shows a "Price type" label with LP, SP and LP & SP', () => {
    open();
    expect(screen.getByText('Price type')).toBeInTheDocument();
    for (const label of ['LP', 'SP', 'LP & SP']) expect(option(label), label).toBeInTheDocument();
  });

  it('AC-28: saving with SP picked sends price_type "selling"', async () => {
    open();
    fireEvent.click(option('SP'));
    expect((await save()).price_type).toBe('selling');
  });

  it('AC-28: LP sends "list" and LP & SP sends "both"', async () => {
    open();
    fireEvent.click(option('LP'));
    expect((await save()).price_type).toBe('list');

    createTemplate.mockClear();
    fireEvent.click(option('LP & SP'));
    expect((await save()).price_type).toBe('both');
  });

  it('AC-28: leaving it unset is allowed and sends null (or omits it)', async () => {
    open();
    const body = await save();
    expect(body.price_type ?? null).toBeNull();
  });

  it('AC-28: pressing the picked option again clears it', async () => {
    open();
    fireEvent.click(option('SP'));
    fireEvent.click(option('SP'));
    const body = await save();
    expect(body.price_type ?? null).toBeNull();
  });
});
