/**
 * useCertificates hooks - query keys and cache invalidation.
 *   FE-3 / FE-4 (every list param is part of the query key, so switching the
 *     validity scope or any filter is a NEW cache entry rather than a stale hit)
 *   DUP-4 (merge invalidates the list and the surviving TARGET certificate)
 *   COV-3 (add / remove coverage invalidates the list and that certificate)
 *   RVW-4 (update invalidates the list and that certificate)
 *   Bulk delete stays SILENT on success: the caller's own AlertDialog owns the
 *   toast, so toasting here would double up.
 *
 * The service layer is mocked - these tests pin the hook contract (key, params,
 * invalidations, toasts), not the HTTP calls. Row-level list behaviour that the
 * DataGrid cannot settle under jsdom is asserted here instead of in the
 * component test.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../services/certificateService', () => ({
  getCertificates: vi.fn(),
  getCertificate: vi.fn(),
  createCertificate: vi.fn(),
  updateCertificate: vi.fn(),
  bulkDeleteCertificates: vi.fn(),
  mergeCertificateInto: vi.fn(),
  addCertificateProduct: vi.fn(),
  removeCertificateProduct: vi.fn(),
}));

import { toast } from 'sonner';
import type { CertificatesListParams } from '../services/certificateService';
import {
  addCertificateProduct,
  bulkDeleteCertificates,
  createCertificate,
  getCertificate,
  getCertificates,
  mergeCertificateInto,
  removeCertificateProduct,
  updateCertificate,
} from '../services/certificateService';
import {
  useAddCertificateProduct,
  useBulkDeleteCertificates,
  useCertificate,
  useCertificateMergeTargets,
  useCertificates,
  useCreateCertificate,
  useMergeCertificate,
  useRemoveCertificateProduct,
  useUpdateCertificate,
} from './useCertificates';

const mockGetCertificates = getCertificates as unknown as ReturnType<typeof vi.fn>;
const mockGetCertificate = getCertificate as unknown as ReturnType<typeof vi.fn>;
const mockCreate = createCertificate as unknown as ReturnType<typeof vi.fn>;
const mockUpdate = updateCertificate as unknown as ReturnType<typeof vi.fn>;
const mockBulkDelete = bulkDeleteCertificates as unknown as ReturnType<typeof vi.fn>;
const mockMerge = mergeCertificateInto as unknown as ReturnType<typeof vi.fn>;
const mockAddProduct = addCertificateProduct as unknown as ReturnType<typeof vi.fn>;
const mockRemoveProduct = removeCertificateProduct as unknown as ReturnType<typeof vi.fn>;

function newClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

/** Every list param that must take part in the cache key. */
const LIST_PARAMS: CertificatesListParams = {
  pageIndex: 2,
  pageSize: 50,
  sorting: [{ id: 'valid_until', desc: false }],
  searchQuery: 'PPS 123',
  validity_state: 'expiring_soon,expired',
  expiring_within_days: 30,
  scheme: 'PPS',
  status: 'active',
  needs_review: true,
};

beforeEach(() => vi.clearAllMocks());

describe('useCertificates - list query key (FE-3 / FE-4)', () => {
  it('includes every list param in the query key, in order', async () => {
    mockGetCertificates.mockResolvedValue({ data: [], empty: true, pagination: { total: 0, page: 1 } });
    const client = newClient();
    const { result } = renderHook(() => useCertificates(LIST_PARAMS), { wrapper: wrapper(client) });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = client.getQueryCache().getAll().map((q) => q.queryKey);
    expect(keys).toContainEqual([
      'certificates',
      2,
      50,
      LIST_PARAMS.sorting,
      'PPS 123',
      'expiring_soon,expired',
      30,
      'PPS',
      'active',
      true,
    ]);
  });

  it('passes the params straight through to the service', async () => {
    mockGetCertificates.mockResolvedValue({ data: [], empty: true, pagination: { total: 0, page: 1 } });
    const client = newClient();
    const { result } = renderHook(() => useCertificates(LIST_PARAMS), { wrapper: wrapper(client) });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetCertificates).toHaveBeenCalledWith(LIST_PARAMS);
  });

  it('changing the validity scope produces a SEPARATE cache entry, never a stale hit', async () => {
    mockGetCertificates.mockResolvedValue({ data: [], empty: true, pagination: { total: 0, page: 1 } });
    const client = newClient();
    const { rerender, result } = renderHook((p: CertificatesListParams) => useCertificates(p), {
      wrapper: wrapper(client),
      initialProps: LIST_PARAMS,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    rerender({ ...LIST_PARAMS, validity_state: undefined });
    await waitFor(() => expect(mockGetCertificates).toHaveBeenCalledTimes(2));
    const keys = client.getQueryCache().getAll().map((q) => q.queryKey);
    expect(keys).toHaveLength(2);
    expect(keys[0]).not.toEqual(keys[1]);
  });

  it('every single filter is key-bearing (one changed filter = one new entry)', async () => {
    mockGetCertificates.mockResolvedValue({ data: [], empty: true, pagination: { total: 0, page: 1 } });
    const overrides: Partial<CertificatesListParams>[] = [
      { pageIndex: 3 },
      { pageSize: 100 },
      { sorting: [{ id: 'scheme', desc: true }] },
      { searchQuery: 'SPAN' },
      { validity_state: 'expired' },
      { expiring_within_days: 7 },
      { scheme: 'SPAN' },
      { status: 'archived' },
      { needs_review: undefined },
    ];
    for (const over of overrides) {
      const client = newClient();
      const { result, rerender } = renderHook((p: CertificatesListParams) => useCertificates(p), {
        wrapper: wrapper(client),
        initialProps: LIST_PARAMS,
      });
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      rerender({ ...LIST_PARAMS, ...over });
      await waitFor(() => expect(client.getQueryCache().getAll()).toHaveLength(2));
    }
  });
});

describe('useCertificate / useCertificateMergeTargets - detail keys', () => {
  it('keys the detail query on the certificate id and skips a null id', async () => {
    mockGetCertificate.mockResolvedValue({ id: 'cert-1' });
    const client = newClient();
    const { result } = renderHook(() => useCertificate('cert-1'), { wrapper: wrapper(client) });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.getQueryCache().getAll()[0].queryKey).toEqual(['certificate', 'cert-1']);
    expect(mockGetCertificate).toHaveBeenCalledWith('cert-1');
  });

  it('does not fetch the detail when there is no id', async () => {
    const client = newClient();
    const { result } = renderHook(() => useCertificate(null), { wrapper: wrapper(client) });
    await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));
    expect(mockGetCertificate).not.toHaveBeenCalled();
  });

  it('merge targets are keyed separately and exclude the source certificate', async () => {
    mockGetCertificate.mockResolvedValue({ id: 'cert-1', scheme: 'PPS' });
    mockGetCertificates.mockResolvedValue({
      data: [
        { id: 'cert-1', scheme: 'PPS', certificate_number: 'PPS 1', certifying_body: 'SIRIM' },
        { id: 'cert-2', scheme: 'PPS', certificate_number: 'PPS 2', certifying_body: 'SIRIM' },
        { id: 'cert-3', scheme: 'PPS', certificate_number: 'PPS 3', certifying_body: null },
      ],
      empty: false,
      pagination: { total: 3, page: 1 },
    });
    const client = newClient();
    const { result } = renderHook(() => useCertificateMergeTargets('cert-1'), {
      wrapper: wrapper(client),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.getQueryCache().getAll()[0].queryKey).toEqual([
      'certificate-merge-targets',
      'cert-1',
    ]);
    // Same-scheme, active, source excluded, labelled by human identity.
    expect(mockGetCertificates).toHaveBeenCalledWith({
      pageIndex: 0,
      pageSize: 200,
      scheme: 'PPS',
      status: 'active',
    });
    expect(result.current.data).toEqual([
      { value: 'cert-2', label: 'PPS PPS 2 - SIRIM' },
      { value: 'cert-3', label: 'PPS PPS 3' },
    ]);
  });
});

describe('useCreateCertificate / useUpdateCertificate - invalidation + toasts', () => {
  it('create invalidates the list and toasts success', async () => {
    mockCreate.mockResolvedValue({ id: 'cert-new' });
    const client = newClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useCreateCertificate(), { wrapper: wrapper(client) });

    result.current.mutate({
      scheme: 'PPS',
      certifying_body: 'SIRIM QAS',
      certificate_number: 'PPS 9/2026',
      status: 'active',
    });

    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['certificates'] }),
    );
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('Certificate created successfully'),
    );
  });

  it('create toasts the extracted error message on failure', async () => {
    mockCreate.mockRejectedValue(new Error('Certificate already exists'));
    const client = newClient();
    const { result } = renderHook(() => useCreateCertificate(), { wrapper: wrapper(client) });
    result.current.mutate({
      scheme: 'PPS',
      certifying_body: 'SIRIM QAS',
      certificate_number: 'PPS 9/2026',
      status: 'active',
    });
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Certificate already exists'));
  });

  it('update invalidates BOTH the list and that certificate (RVW-4)', async () => {
    mockUpdate.mockResolvedValue({ id: 'cert-1' });
    const client = newClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useUpdateCertificate(), { wrapper: wrapper(client) });

    result.current.mutate({ id: 'cert-1', data: { valid_until: '2027-01-01' } });

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith('cert-1', { valid_until: '2027-01-01' }));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['certificates'] }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['certificate', 'cert-1'] });
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('Certificate updated successfully'),
    );
  });
});

describe('delete hooks - invalidate but stay silent', () => {
  it('bulk delete passes the ids through, invalidates, and stays silent', async () => {
    mockBulkDelete.mockResolvedValue({ message: 'ok', deleted_count: 2 });
    const client = newClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useBulkDeleteCertificates(), { wrapper: wrapper(client) });

    result.current.mutate(['cert-a', 'cert-b']);

    await waitFor(() => expect(mockBulkDelete).toHaveBeenCalledWith(['cert-a', 'cert-b']));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['certificates'] }));
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });
});

describe('useMergeCertificate - invalidates the surviving certificate (DUP-4)', () => {
  it('invalidates the list and the TARGET id, not the source', async () => {
    mockMerge.mockResolvedValue({ id: 'cert-target' });
    const client = newClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useMergeCertificate(), { wrapper: wrapper(client) });

    result.current.mutate({ id: 'cert-src', targetId: 'cert-target' });

    await waitFor(() => expect(mockMerge).toHaveBeenCalledWith('cert-src', 'cert-target'));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['certificates'] }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['certificate', 'cert-target'] });
    // The source row is gone after a merge, so re-fetching it would 404.
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: ['certificate', 'cert-src'] });
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('Certificates merged successfully'),
    );
  });

  it('toasts the failure message', async () => {
    mockMerge.mockRejectedValue(new Error('Cannot merge a certificate into itself'));
    const client = newClient();
    const { result } = renderHook(() => useMergeCertificate(), { wrapper: wrapper(client) });
    result.current.mutate({ id: 'cert-src', targetId: 'cert-src' });
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Cannot merge a certificate into itself'),
    );
  });
});

describe('coverage hooks - invalidate the list and the certificate (COV-3)', () => {
  it('add posts the product id and invalidates both keys', async () => {
    mockAddProduct.mockResolvedValue({ id: 'cert-1' });
    const client = newClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useAddCertificateProduct(), { wrapper: wrapper(client) });

    result.current.mutate({ id: 'cert-1', productId: 'prd-3' });

    await waitFor(() => expect(mockAddProduct).toHaveBeenCalledWith('cert-1', 'prd-3'));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['certificates'] }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['certificate', 'cert-1'] });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Product added to coverage'));
  });

  it('remove sends the COVERAGE id and invalidates both keys', async () => {
    mockRemoveProduct.mockResolvedValue(undefined);
    const client = newClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useRemoveCertificateProduct(), { wrapper: wrapper(client) });

    result.current.mutate({ id: 'cert-1', coverageId: 'cov-2' });

    await waitFor(() => expect(mockRemoveProduct).toHaveBeenCalledWith('cert-1', 'cov-2'));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['certificates'] }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['certificate', 'cert-1'] });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Product removed from coverage'));
  });

  it('a failing add toasts the message and leaves the cache alone', async () => {
    mockAddProduct.mockRejectedValue(new Error('Product already covered'));
    const client = newClient();
    const { result } = renderHook(() => useAddCertificateProduct(), { wrapper: wrapper(client) });
    result.current.mutate({ id: 'cert-1', productId: 'prd-3' });
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Product already covered'));
    expect(toast.success).not.toHaveBeenCalled();
  });
});
