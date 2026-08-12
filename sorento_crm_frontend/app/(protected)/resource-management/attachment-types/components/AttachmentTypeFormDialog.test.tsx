/**
 * AttachmentTypeFormDialog - the certificate switch.
 *
 * The external product-attachment endpoint honours the certificate fields on an
 * n8n payload ONLY when the attachment's type has `is_certificate = true`. That
 * flag shipped with no UI, so the register could not be switched on for a type
 * at all: these tests pin the control and its payload so it cannot go missing
 * again.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

const hooks = vi.hoisted(() => ({
  createAsync: vi.fn().mockResolvedValue({}),
  updateAsync: vi.fn().mockResolvedValue({}),
  useAttachmentType: vi.fn(),
}));

vi.mock('../hooks/useAttachmentTypes', () => ({
  useCreateAttachmentType: () => ({ mutateAsync: hooks.createAsync, isPending: false }),
  useUpdateAttachmentType: () => ({ mutateAsync: hooks.updateAsync, isPending: false }),
  useAttachmentType: (...a: unknown[]) => hooks.useAttachmentType(...a),
}));

import AttachmentTypeFormDialog from './AttachmentTypeFormDialog';

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  hooks.useAttachmentType.mockReturnValue({ data: undefined, isLoading: false });
});

function renderCreate() {
  return render(<AttachmentTypeFormDialog open onOpenChange={vi.fn()} />);
}

function fillRequired() {
  fireEvent.change(screen.getByLabelText(/Type Name/i), { target: { value: 'Certification' } });
  fireEvent.change(screen.getByLabelText(/Allowed Extensions/i), { target: { value: 'pdf' } });
}

describe('AttachmentTypeFormDialog - certificate switch', () => {
  it('offers the certificate checkbox, off by default', () => {
    renderCreate();
    const box = screen.getByRole('checkbox', { name: /Files of this type are certificates/i });
    expect(box).toBeInTheDocument();
    expect(box).not.toBeChecked();
  });

  it('reveals the validity ceiling only once the type is a certificate type', () => {
    renderCreate();
    expect(screen.queryByLabelText(/Maximum validity/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: /Files of this type are certificates/i }));
    expect(screen.getByLabelText(/Maximum validity \(months\)/i)).toBeInTheDocument();
  });

  it('sends is_certificate and the ceiling on create', async () => {
    renderCreate();
    fillRequired();
    fireEvent.click(screen.getByRole('checkbox', { name: /Files of this type are certificates/i }));
    fireEvent.change(screen.getByLabelText(/Maximum validity \(months\)/i), {
      target: { value: '36' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Create$/ }));

    await waitFor(() => expect(hooks.createAsync).toHaveBeenCalledTimes(1));
    expect(hooks.createAsync.mock.calls[0][0]).toMatchObject({
      is_certificate: true,
      max_validity_months: 36,
    });
  });

  it('sends a blank ceiling as null, not 0', async () => {
    renderCreate();
    fillRequired();
    fireEvent.click(screen.getByRole('checkbox', { name: /Files of this type are certificates/i }));
    fireEvent.click(screen.getByRole('button', { name: /^Create$/ }));

    await waitFor(() => expect(hooks.createAsync).toHaveBeenCalledTimes(1));
    expect(hooks.createAsync.mock.calls[0][0]).toMatchObject({
      is_certificate: true,
      max_validity_months: null,
    });
  });

  it('loads the saved flag when editing, so it is not silently reset to off', () => {
    hooks.useAttachmentType.mockReturnValue({
      data: {
        id: 'type-1',
        type_name: 'Certification',
        description: 'Certification / Certificate / Cert by Purchasing',
        allowed_extensions: 'pdf,jpg',
        max_file_size_mb: 10,
        max_count_per_entity: null,
        supports_field_linkage: false,
        is_certificate: true,
        max_validity_months: 60,
        created_at: new Date('2026-01-01'),
      },
      isLoading: false,
    });
    render(<AttachmentTypeFormDialog open onOpenChange={vi.fn()} attachmentTypeId="type-1" />);
    expect(
      screen.getByRole('checkbox', { name: /Files of this type are certificates/i }),
    ).toBeChecked();
    expect((screen.getByLabelText(/Maximum validity \(months\)/i) as HTMLInputElement).value).toBe(
      '60',
    );
  });
});
