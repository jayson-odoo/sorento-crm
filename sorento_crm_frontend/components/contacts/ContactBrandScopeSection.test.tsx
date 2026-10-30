/**
 * ContactBrandScopeSection - the "Brands" card on the contact Profile tab (CONTACT-BRAND-SCOPE,
 * AC-4) with the allowed item classes picker under the brands (TAG-BRAND-CLASS AC-6).
 *
 *   - empty (unscoped) shows the "All brands" placeholder
 *   - a scoped contact shows its brand NAMES, never an id
 *   - Save PUTs the picked ids to /api/v1/user-management/contacts/{id}/brands
 *   - clearing every brand and saving sends `[]` (the server stores NULL = all brands)
 *   - a failed save toasts the server message
 *
 * Mocked at the `apiFetch` boundary so the card, hook and service are all real; the shared
 * multi-select is a deterministic stub (the technique StockVisibilitySection.test.tsx uses)
 * that exposes its placeholder, its selected ids and whether it can be cleared.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  custom: vi.fn(),
  message: vi.fn(),
  dismiss: vi.fn(),
}));
vi.mock('@/lib/toast', () => ({ toast: toastMock }));

const apiFetchMock = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...a: unknown[]) => apiFetchMock(...a),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    id,
    value,
    onChange,
    options,
    placeholder,
    clearable,
  }: {
    id?: string;
    value: string[];
    onChange: (v: string[]) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    clearable?: boolean;
  }) => (
    <div
      data-testid={id === 'contact-brand-scope' ? 'brands-picker' : id}
      data-placeholder={placeholder ?? ''}
      data-value={value.join(',')}
      data-clearable={String(clearable)}
    >
      {value.length === 0 ? <span>{placeholder}</span> : null}
      {(options ?? [])
        .filter((o) => value.includes(o.value))
        .map((o) => (
          <span key={o.value} data-testid="brand-chip">
            {o.label}
          </span>
        ))}
      {(options ?? []).map((o) => (
        <button key={o.value} type="button" onClick={() => onChange([...value, o.value])}>
          pick {o.label}
        </button>
      ))}
      <button type="button" onClick={() => onChange([])}>
        clear {id}
      </button>
    </div>
  ),
}));

const NO_CLASS = { code: '__NONE__', name: 'No class' };
const DIY = { code: 'DIY', name: 'SORENTO LITE - DIY' };
const SERENE = { code: 'SERENE', name: 'SORENTO SERENE SERIES' };
const MOCHA = { id: '11111111-1111-4111-8111-111111111111', brand_name: 'Mocha' };
const SORENTO = { id: '22222222-2222-4222-8222-222222222222', brand_name: 'Sorento' };

function ok(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body, headers: new Headers() } as unknown as Response;
}

function serve(saved: { id: string; brand_name: string }[], savedCodes: string[] = []) {
  apiFetchMock.mockImplementation(async (url: string, init?: { method?: string; body?: string }) => {
    if (String(url).includes('/master-data/brands/select')) return ok([MOCHA, SORENTO]);
    if (String(url).includes('/contacts/c1/brands')) {
      if (init?.method === 'PUT') {
        const body = JSON.parse(init.body ?? '{}');
        const ids = body.brand_ids as string[];
        return ok({
          brand_ids: ids,
          brands: [MOCHA, SORENTO].filter((b) => ids.includes(b.id)),
          allowed_item_class_codes: body.allowed_item_class_codes ?? [],
          item_class_options: [NO_CLASS, DIY, SERENE],
        });
      }
      return ok({
        brand_ids: saved.map((b) => b.id),
        brands: saved,
        allowed_item_class_codes: savedCodes,
        item_class_options: [NO_CLASS, DIY, SERENE],
      });
    }
    return ok({});
  });
}

import ContactBrandScopeSection from './ContactBrandScopeSection';

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactBrandScopeSection contactId="c1" />
    </QueryClientProvider>,
  );
}

function putCalls() {
  return apiFetchMock.mock.calls.filter(([, init]) => (init as { method?: string } | undefined)?.method === 'PUT');
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => cleanup());

describe('ContactBrandScopeSection', () => {
  it('reads "All brands" when the contact has none set, and the picker can be cleared', async () => {
    serve([]);
    renderCard();
    const picker = await screen.findByTestId('brands-picker');
    expect(picker).toHaveAttribute('data-placeholder', 'All brands');
    expect(picker).toHaveAttribute('data-clearable', 'true');
    expect(picker).toHaveAttribute('data-value', '');
  });

  it('shows the saved brands by name and never an id', async () => {
    serve([MOCHA]);
    renderCard();
    await waitFor(() => expect(screen.getAllByTestId('brand-chip').map((c) => c.textContent)).toEqual(['Mocha']));
    expect(document.body.textContent).not.toContain(MOCHA.id);
  });

  it('Save sends the picked brand ids with PUT', async () => {
    serve([]);
    renderCard();
    fireEvent.click(await screen.findByText('pick Mocha'));
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(putCalls()).toHaveLength(1));
    const [url, init] = putCalls()[0] as [string, { body: string }];
    expect(url).toContain('/api/v1/user-management/contacts/c1/brands');
    expect(JSON.parse(init.body)).toEqual({ brand_ids: [MOCHA.id], allowed_item_class_codes: [] });
    await waitFor(() => expect(toastMock.success).toHaveBeenCalled());
  });

  it('clearing every brand and saving sends an empty list (all brands)', async () => {
    serve([MOCHA, SORENTO]);
    renderCard();
    await waitFor(() => expect(screen.getAllByTestId('brand-chip')).toHaveLength(2));
    fireEvent.click(screen.getByText('clear contact-brand-scope'));
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(putCalls()).toHaveLength(1));
    expect(JSON.parse((putCalls()[0][1] as { body: string }).body)).toEqual({
      brand_ids: [],
      allowed_item_class_codes: [],
    });
  });

  it('a rejected save toasts the server message', async () => {
    apiFetchMock.mockImplementation(async (url: string, init?: { method?: string }) => {
      if (String(url).includes('/master-data/brands/select')) return ok([MOCHA]);
      if (init?.method === 'PUT') {
        return {
          ok: false,
          status: 422,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ message: 'Unknown brand id' }),
          text: async () => JSON.stringify({ message: 'Unknown brand id' }),
        } as unknown as Response;
      }
      return ok({ brand_ids: [], brands: [] });
    });
    renderCard();
    fireEvent.click(await screen.findByText('pick Mocha'));
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith(expect.stringContaining('Unknown brand id')));
  });

  describe('allowed item classes (one list under Brands)', () => {
    it('shows one "Allowed item classes" picker reading "All classes", with All brands too', async () => {
      serve([]);
      renderCard();
      const picker = await screen.findByTestId('contact-item-classes');
      expect(picker).toHaveAttribute('data-placeholder', 'All classes');
      expect(picker).toHaveAttribute('data-clearable', 'true');
      expect(screen.getByText('Allowed item classes')).toBeInTheDocument();
      expect(screen.queryByText(/Mocha classes|Sorento classes/)).toBeNull();
    });

    it('the first class picked also ticks "No class", and Save sends the codes (the Serene case)', async () => {
      serve([]);
      renderCard();
      const picker = await screen.findByTestId('contact-item-classes');
      fireEvent.click(within(picker).getByText(`pick ${DIY.name}`));
      await waitFor(() => expect(picker).toHaveAttribute('data-value', `${NO_CLASS.code},${DIY.code}`));
      fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
      await waitFor(() => expect(putCalls()).toHaveLength(1));
      expect(JSON.parse((putCalls()[0][1] as { body: string }).body)).toEqual({
        brand_ids: [],
        allowed_item_class_codes: [NO_CLASS.code, DIY.code],
      });
    });

    it('changing the brands keeps the allowed classes', async () => {
      serve([], [DIY.code]);
      renderCard();
      await waitFor(() =>
        expect(screen.getByTestId('contact-item-classes')).toHaveAttribute('data-value', DIY.code),
      );
      fireEvent.click(within(screen.getByTestId('brands-picker')).getByText('pick Sorento'));
      fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
      await waitFor(() => expect(putCalls()).toHaveLength(1));
      expect(JSON.parse((putCalls()[0][1] as { body: string }).body)).toEqual({
        brand_ids: [SORENTO.id],
        allowed_item_class_codes: [DIY.code],
      });
    });

    it('a saved code the options no longer carry shows as the code, never an id', async () => {
      serve([], ['RETIRED']);
      renderCard();
      const picker = await screen.findByTestId('contact-item-classes');
      await waitFor(() => expect(within(picker).getByTestId('brand-chip')).toHaveTextContent('RETIRED'));
    });
  });
});
