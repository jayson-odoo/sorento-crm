/**
 * UserProfileEditDialog - product-discontinued scope wiring (AC-15, AC-18).
 *
 * Focused on the dialog's OWN state, not the editor's: switching a discontinued
 * toggle off-to-on pre-populates one all/all row when there were none, deleting
 * every row afterwards does not get re-populated, and the PUT body carries
 * `product_discontinued_scopes` built from whatever the editor currently holds.
 * `ProductDiscontinuedScopeEditor` itself is stubbed (it has its own test file);
 * this one drives the dialog's `useEffect`/state around it.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { email: 'admin@zzt.test' } } }),
}));

vi.mock('@/lib/is-superadmin', () => ({ isSuperadminUser: () => false }));

vi.mock('@/app/(protected)/system-management/companies/services/companyService', () => ({
  getCompaniesSelect: vi.fn().mockResolvedValue([]),
}));

vi.mock('@/app/providers/CompanyProvider', () => ({
  useCompany: () => ({
    companies: [
      { id: 'co-1', name: 'Sorento', code: 'SRT' },
      { id: 'co-2', name: 'Mocha', code: 'MCH' },
    ],
  }),
}));

vi.mock('../../../roles/hooks/use-role-select-query', () => ({
  useRoleSelectQuery: () => ({ data: [{ id: 'role-1', name: 'Staff' }] }),
}));

// Deterministic stub: exposes the row count/shape as text and two buttons the
// test can drive, rather than re-testing the real editor's own internals here.
const editorProps = vi.hoisted(() => ({ current: null as unknown }));
vi.mock('./product-discontinued-scope-editor', () => ({
  default: (props: {
    rows: { companyId: string | null; brandIds: string[] }[];
    onChange: (rows: unknown[]) => void;
  }) => {
    editorProps.current = props;
    return (
      <div data-testid="scope-editor-stub">
        <span data-testid="scope-row-count">{props.rows.length}</span>
        <span data-testid="scope-row-shape">
          {JSON.stringify(props.rows.map((r) => ({ companyId: r.companyId, brandIds: r.brandIds })))}
        </span>
        <button type="button" onClick={() => props.onChange([])}>
          clear-all-rows
        </button>
      </div>
    );
  },
}));

import UserProfileEditDialog from './user-profile-edit-dialog';
import type { User } from '@/app/models/user';

const BASE_USER: User = {
  id: 'user-1',
  name: 'Kia Yee',
  email: 'kiayee@zzt.test',
  status: 'ACTIVE',
  roles: [{ id: 'role-1', name: 'Staff' }],
  notifyEmailOnProductDiscontinued: false,
  notifyWhatsappOnProductDiscontinued: false,
  productDiscontinuedScopes: [],
} as unknown as User;

function okJson(body: unknown) {
  return Promise.resolve({ ok: true, json: async () => body } as Response);
}

function renderDialog(user: User = BASE_USER) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const closeDialog = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <UserProfileEditDialog open closeDialog={closeDialog} user={user} />
    </QueryClientProvider>,
  );
  return { closeDialog };
}

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockImplementation((url: string, init?: { method?: string }) => {
    if (url.includes('/roles') && init?.method === 'PUT') {
      return okJson({ success: true });
    }
    if (url.includes('/roles')) return okJson([{ id: 'role-1', name: 'Staff' }]);
    if (url.includes('/select')) return okJson([]);
    if (url.includes('/respond-users')) return okJson([]);
    if (init?.method === 'PUT') return okJson(BASE_USER);
    return okJson(BASE_USER);
  });
});

afterEach(() => cleanup());

describe('UserProfileEditDialog - discontinued scope pre-population (AC-15)', () => {
  it('a user with zero scopes and toggles off starts the editor with zero rows', async () => {
    renderDialog();
    await waitFor(() => expect(screen.getByTestId('scope-row-count')).toHaveTextContent('0'));
  });

  it('switching email-on-discontinued ON with zero rows pre-populates one all/all row', async () => {
    renderDialog();
    await waitFor(() => expect(screen.getByTestId('scope-row-count')).toHaveTextContent('0'));

    fireEvent.click(
      screen.getByRole('checkbox', { name: /email on products discontinued/i }),
    );

    await waitFor(() => expect(screen.getByTestId('scope-row-count')).toHaveTextContent('1'));
    const shape = JSON.parse(screen.getByTestId('scope-row-shape').textContent || '[]');
    expect(shape).toEqual([{ companyId: null, brandIds: [] }]);
  });

  it('switching whatsapp-on-discontinued ON also pre-populates when email stays off', async () => {
    renderDialog();
    fireEvent.click(
      screen.getByRole('checkbox', { name: /whatsapp on products discontinued/i }),
    );
    await waitFor(() => expect(screen.getByTestId('scope-row-count')).toHaveTextContent('1'));
  });

  it('deleting every row after pre-population does not get re-populated', async () => {
    renderDialog();
    fireEvent.click(
      screen.getByRole('checkbox', { name: /email on products discontinued/i }),
    );
    await waitFor(() => expect(screen.getByTestId('scope-row-count')).toHaveTextContent('1'));

    fireEvent.click(screen.getByText('clear-all-rows'));
    await waitFor(() => expect(screen.getByTestId('scope-row-count')).toHaveTextContent('0'));

    // Force another render pass (a different, unrelated toggle) - the effect's
    // deps are [open, discontinuedNotifyOn], both unchanged, so it must not fire.
    fireEvent.click(screen.getByRole('checkbox', { name: /email on assignment/i }));
    await waitFor(() =>
      expect(screen.getByRole('checkbox', { name: /email on assignment/i })).not.toBeChecked(),
    );
    expect(screen.getByTestId('scope-row-count')).toHaveTextContent('0');
  });

  it('a user opened with an existing scope keeps it (no forced all/all)', async () => {
    const user: User = {
      ...BASE_USER,
      notifyEmailOnProductDiscontinued: true,
      productDiscontinuedScopes: [
        { company_id: 'co-1', company_name: 'Sorento', brand_id: null },
      ],
    } as unknown as User;
    renderDialog(user);
    await waitFor(() => expect(screen.getByTestId('scope-row-count')).toHaveTextContent('1'));
    const shape = JSON.parse(screen.getByTestId('scope-row-shape').textContent || '[]');
    expect(shape).toEqual([{ companyId: 'co-1', brandIds: [] }]);
  });
});

describe('UserProfileEditDialog - PUT body carries product_discontinued_scopes (AC-12 FE side)', () => {
  it('Save Changes sends product_discontinued_scopes built from the current rows', async () => {
    renderDialog();
    fireEvent.click(
      screen.getByRole('checkbox', { name: /email on products discontinued/i }),
    );
    await waitFor(() => expect(screen.getByTestId('scope-row-count')).toHaveTextContent('1'));

    const saveButton = screen.getByRole('button', { name: /save changes/i });
    await waitFor(() => expect(saveButton).not.toBeDisabled());
    fireEvent.click(saveButton);

    await waitFor(() => {
      const putCall = apiFetch.mock.calls.find(
        (call) =>
          typeof call[0] === 'string' &&
          call[0] === '/api/user-management/users/user-1' &&
          call[1]?.method === 'PUT',
      );
      expect(putCall).toBeTruthy();
    });

    const putCall = apiFetch.mock.calls.find(
      (call) =>
        typeof call[0] === 'string' &&
        call[0] === '/api/user-management/users/user-1' &&
        call[1]?.method === 'PUT',
    )!;
    const body = JSON.parse(putCall[1].body as string);
    expect(body.product_discontinued_scopes).toEqual([{ company_id: null, brand_id: null }]);
  });
});
