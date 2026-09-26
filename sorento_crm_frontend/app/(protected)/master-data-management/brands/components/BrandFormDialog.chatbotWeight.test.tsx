/**
 * R1 (owner console test of round 3 on PR #833, 27 Sep 2026): the "Chatbot brand weight"
 * number on the create/edit dialog the Brands list mounts, in place of the retired
 * "Chatbot default brand" switch.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const createMutateAsync = vi.fn().mockResolvedValue({});
const updateMutateAsync = vi.fn().mockResolvedValue({});
const useBrandMock = vi.fn(() => ({ data: undefined, isLoading: false }));
vi.mock('../hooks/useBrands', () => ({
  useCreateBrand: () => ({ mutateAsync: createMutateAsync, isPending: false }),
  useUpdateBrand: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
  useBrand: (id: string | null) => useBrandMock(id),
}));

vi.mock(
  '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes',
  () => ({
    useContactAccessTypes: () => ({ data: [] }),
  }),
);

import BrandFormDialog from './BrandFormDialog';

beforeEach(() => {
  vi.clearAllMocks();
  useBrandMock.mockReturnValue({ data: undefined, isLoading: false });
});

function fillRequiredFields() {
  fireEvent.change(screen.getByLabelText(/Brand Code/i), {
    target: { value: 'ZZTX-001' },
  });
  fireEvent.change(screen.getByLabelText(/Brand Name/i), {
    target: { value: 'ZZT Test Brand' },
  });
}

describe('BrandFormDialog - Chatbot brand weight (R1)', () => {
  it('starts at 0 for a new brand, and there is no default switch', () => {
    render(<BrandFormDialog open onOpenChange={() => {}} />);

    expect(
      (screen.getByLabelText('Chatbot brand weight') as HTMLInputElement).value,
    ).toBe('0');
    expect(screen.queryByLabelText('Chatbot default brand')).toBeNull();
  });

  it('sends the typed weight as a number in the create payload', async () => {
    render(<BrandFormDialog open onOpenChange={() => {}} />);
    fillRequiredFields();

    fireEvent.change(screen.getByLabelText('Chatbot brand weight'), {
      target: { value: '0.5' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const [payload] = createMutateAsync.mock.calls[0];
    expect(payload.chatbot_weight).toBe(0.5);
  });

  it('reflects the stored weight on edit and an untouched submit keeps it', async () => {
    useBrandMock.mockReturnValue({
      data: {
        id: 'brand-1',
        brand_code: 'SRT',
        brand_name: 'Sorento',
        description: null,
        is_active: true,
        access_levels: [],
        flows_to_purchasing: true,
        chatbot_weight: 1.5,
      },
      isLoading: false,
    });

    render(<BrandFormDialog open onOpenChange={() => {}} brandId="brand-1" />);

    const input = (await screen.findByLabelText('Chatbot brand weight')) as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe('1.5'));

    fireEvent.click(screen.getByRole('button', { name: /^Update$/i }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const [{ data: payload }] = updateMutateAsync.mock.calls[0];
    expect(payload.chatbot_weight).toBe(1.5);
  });

  it('refuses a negative weight', async () => {
    render(<BrandFormDialog open onOpenChange={() => {}} />);
    fillRequiredFields();

    fireEvent.change(screen.getByLabelText('Chatbot brand weight'), {
      target: { value: '-1' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }));

    await screen.findByText(/0 or more/i);
    expect(createMutateAsync).not.toHaveBeenCalled();
  });

  // PR #833 round 5 N3: the server takes 0 to 9999, so the dialog does too.
  it('bounds the input to 0 to 9999', () => {
    render(<BrandFormDialog open onOpenChange={() => {}} />);

    const input = screen.getByLabelText('Chatbot brand weight') as HTMLInputElement;
    expect(input.min).toBe('0');
    expect(input.max).toBe('9999');
  });

  it('refuses a weight above 9999 instead of sending it', async () => {
    render(<BrandFormDialog open onOpenChange={() => {}} />);
    fillRequiredFields();

    fireEvent.change(screen.getByLabelText('Chatbot brand weight'), {
      target: { value: '10000' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }));

    await screen.findByText(/9999 or less/i);
    expect(createMutateAsync).not.toHaveBeenCalled();
  });
});
