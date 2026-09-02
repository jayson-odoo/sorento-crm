/**
 * CertificateMergeDialog - "merge as a revision of ...".
 *   DUP-6 (the merge sits behind an AlertDialog naming BOTH certificates and
 *     the revision count being moved - never a one-click. Copy: "Confirm merge"
 *     / "This action cannot be undone")
 *   DUP-4 (the merge posts source id + target id; the caller is handed the
 *     TARGET id so it can route to the surviving certificate)
 *   FE-8 (two steps: pick, then confirm with destructive styling)
 *   loading / empty target-list states
 *
 * SearchableSelect is stubbed to a native <select> with aria-label={placeholder}
 * so target selection is deterministic under jsdom.
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

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    disabled,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
    disabled?: boolean;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const hooks = vi.hoisted(() => ({
  useCertificateMergeTargets: vi.fn(),
  mergeMutate: vi.fn(),
}));
vi.mock('../hooks/useCertificates', () => ({
  useCertificateMergeTargets: (...a: unknown[]) => hooks.useCertificateMergeTargets(...a),
  useMergeCertificate: () => ({ mutate: hooks.mergeMutate, isPending: false }),
}));

import CertificateMergeDialog from './CertificateMergeDialog';
import type { Certificate, CertificateRevision } from '../types/certificate.types';

function rev(no: number): CertificateRevision {
  return {
    id: `rev-${no}`,
    revision_no: no,
    issued_at: null,
    valid_from: null,
    valid_until: null,
    is_current: no === 1,
    source: 'ai',
    needs_review: false,
    review_reasons: [],
    unmatched_products: [],
    access_levels: [],
    attachment_filename: null,
    attachment_is_deleted: null,
    created_at: '2024-01-01T00:00:00',
      };
}

function source(over: Partial<Certificate> = {}): Certificate {
  return {
    id: 'cert-src',
    scheme: 'PPS',
    certifying_body: 'SIRIM QAS',
    certificate_number: 'PPS 123/2024',
    issuer: null,
    title: null,
    status: 'active',
    validity_state: 'valid',
    is_expired: false,
    valid_from: null,
    valid_until: null,
    days_until_expiry: null,
    covered_product_count: 2,
    needs_review: false,
    review_reasons: [],
    possible_duplicate_of_certificate_id: null,
    possible_duplicate_of: null,
    current_revision: null,
    revisions: [rev(1), rev(2)],
    products: [],
    unmatched_products: [],
    reminders: [],
    created_at: '2024-01-01T00:00:00',
    updated_at: '2024-01-01T00:00:00',
    ...over,
  } as Certificate;
}

const TARGETS = [
  { value: 'cert-target', label: 'PPS PPS 122/2021 - SIRIM QAS' },
  { value: 'cert-other', label: 'PPS PPS 077/2019 - SIRIM QAS' },
];

function renderDialog(over: { certificate?: Certificate; onMerged?: (id: string) => void } = {}) {
  const onMerged = over.onMerged ?? vi.fn();
  const onOpenChange = vi.fn();
  render(
    <CertificateMergeDialog
      open
      onOpenChange={onOpenChange}
      certificate={over.certificate ?? source()}
      onMerged={onMerged}
    />,
  );
  return { onMerged, onOpenChange };
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  hooks.useCertificateMergeTargets.mockReturnValue({ data: TARGETS, isLoading: false });
});

describe('CertificateMergeDialog - step 1, pick the target', () => {
  it('names the source certificate in the title and previews what moves', () => {
    renderDialog();
    expect(screen.getByText('Merge PPS PPS 123/2024 as a revision')).toBeInTheDocument();
    expect(
      screen.getByText(/2 revisions and 2 covered products will move across\./i),
    ).toBeInTheDocument();
  });

  it('singularises the preview for one revision and one covered product', () => {
    renderDialog({ certificate: source({ revisions: [rev(1)], covered_product_count: 1 }) });
    expect(
      screen.getByText(/1 revision and 1 covered product will move across\./i),
    ).toBeInTheDocument();
  });

  it('Continue is disabled until a target is picked', () => {
    renderDialog();
    expect(screen.getByRole('button', { name: /^Continue$/ })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Select a certificate'), {
      target: { value: 'cert-target' },
    });
    expect(screen.getByRole('button', { name: /^Continue$/ })).toBeEnabled();
  });

  it('shows a loading placeholder and a disabled picker while targets load', () => {
    hooks.useCertificateMergeTargets.mockReturnValue({ data: undefined, isLoading: true });
    renderDialog();
    expect(screen.getByLabelText('Loading certificates...')).toBeDisabled();
  });

  it('pre-selects the suspected duplicate when there is one', () => {
    renderDialog({
      certificate: source({ possible_duplicate_of_certificate_id: 'cert-target' }),
    });
    expect(screen.getByLabelText('Select a certificate')).toHaveValue('cert-target');
    expect(screen.getByRole('button', { name: /^Continue$/ })).toBeEnabled();
  });
});

describe('CertificateMergeDialog - step 2, the confirmation (DUP-6)', () => {
  function reachConfirm(over: Parameters<typeof renderDialog>[0] = {}) {
    const handles = renderDialog(over);
    fireEvent.change(screen.getByLabelText('Select a certificate'), {
      target: { value: 'cert-target' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Continue$/ }));
    return handles;
  }

  it('names BOTH certificates and the revision count being moved', async () => {
    reachConfirm();
    expect(await screen.findByText('Confirm merge')).toBeInTheDocument();
    const copy = screen.getByText(/will be merged into/i).textContent ?? '';
    // Source identity.
    expect(copy).toContain('PPS PPS 123/2024');
    // Target identity, by its human label - never an id.
    expect(copy).toContain('PPS PPS 122/2021 - SIRIM QAS');
    expect(copy).not.toContain('cert-target');
    // The revision count being moved.
    expect(copy).toMatch(/2 revisions/);
    expect(copy).toMatch(/This action cannot be undone/i);
  });

  it('singularises the revision count in the confirmation', async () => {
    reachConfirm({ certificate: source({ revisions: [rev(1)] }) });
    const copy = (await screen.findByText(/will be merged into/i)).textContent ?? '';
    expect(copy).toMatch(/\b1 revision\b/);
    expect(copy).not.toMatch(/1 revisions/);
  });

  it('does not merge until the destructive confirm is clicked', async () => {
    reachConfirm();
    await screen.findByText('Confirm merge');
    expect(hooks.mergeMutate).not.toHaveBeenCalled();
    const confirm = screen.getByRole('button', { name: /^Merge$/ });
    expect(confirm.className).toContain('bg-destructive');
    fireEvent.click(confirm);
    await waitFor(() => expect(hooks.mergeMutate).toHaveBeenCalledTimes(1));
    expect(hooks.mergeMutate.mock.calls[0][0]).toEqual({
      id: 'cert-src',
      targetId: 'cert-target',
    });
  });

  it('hands the caller the TARGET id after a successful merge (DUP-4)', async () => {
    hooks.mergeMutate.mockImplementation((_vars: unknown, opts: { onSuccess?: () => void }) =>
      opts?.onSuccess?.(),
    );
    const { onMerged, onOpenChange } = reachConfirm();
    fireEvent.click(await screen.findByRole('button', { name: /^Merge$/ }));
    await waitFor(() => expect(onMerged).toHaveBeenCalledWith('cert-target'));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('cancelling the confirmation returns to the picker without merging', async () => {
    reachConfirm();
    fireEvent.click(await screen.findByRole('button', { name: /^Cancel$/ }));
    await waitFor(() =>
      expect(screen.getByText('Merge PPS PPS 123/2024 as a revision')).toBeInTheDocument(),
    );
    expect(hooks.mergeMutate).not.toHaveBeenCalled();
  });
});
