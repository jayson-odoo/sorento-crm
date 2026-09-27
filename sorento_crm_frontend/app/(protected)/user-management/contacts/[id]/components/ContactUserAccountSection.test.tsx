/**
 * "User account" (s3-contract.md 2.4, AC-53): always rendered, explicit empty
 * state - "No user yet" with Create user / Link existing user, or the linked
 * user's name, roles and Unlink as a 5-second deferred action (no dialog).
 *
 * `UserAddDialog` is stubbed to a marker so this file stays about the
 * SECTION's own wiring (which contact it locks, when it opens) - the dialog's
 * own contract is `user-add-dialog.s3.test.tsx`'s job.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { RespondContact } from '../../types/contact.types';

/** A real-shaped UUID, so the "no UUID in rendered text" checks mean something. */
const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

const permsRef = vi.hoisted(() => ({
  view: true,
  add: true,
  edit: true,
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => {
    if (slug === 'user_management.users.view') return permsRef.view;
    if (slug === 'user_management.users.add') return permsRef.add;
    if (slug === 'user_management.users.edit') return permsRef.edit;
    return false;
  },
}));

const deferredActionInput = vi.fn();
let unlinkPending: { id: string } | null = null;
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: (input: unknown) => {
    deferredActionInput(input);
    return {
      pending: unlinkPending,
      isPending: !!unlinkPending,
      isBlocked: false,
      start: vi.fn(),
      cancel: vi.fn(),
      countdown: null,
    };
  },
}));

// Fix round 2, S2: user selects go through the shared `userSelectService`
// (CLAUDE.md hard rule), not a per-feature `/users/select` fetcher.
const getUsersSelectMock = vi.fn();
vi.mock('@/services/userSelectService', () => ({
  getUsersSelect: (...a: unknown[]) => getUsersSelectMock(...a),
}));
const updateUserContactLinkMock = vi.fn();
vi.mock('../../../users/services/userService', () => ({
  updateUserContactLink: (...a: unknown[]) => updateUserContactLinkMock(...a),
}));

const userAddDialogSpy = vi.fn();
vi.mock('../../../users/components/user-add-dialog', () => ({
  default: (props: { open: boolean; contact?: { id: string } }) => {
    userAddDialogSpy(props);
    return props.open ? (
      <div data-testid="user-add-dialog-open">locked-contact:{props.contact?.id}</div>
    ) : null;
  },
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import ContactUserAccountSection from './ContactUserAccountSection';

const CONTACT_ID = 'f6666666-6666-4666-8666-666666666666';
const USER_ID = 'a7777777-7777-4777-8777-777777777777';

function contact(over: Partial<RespondContact> = {}): RespondContact {
  return {
    id: CONTACT_ID,
    phone_number: '+60123456789',
    name: 'Aisyah Rahman',
    linked_user: null,
    created_at: new Date('2026-01-01'),
    updated_at: new Date('2026-01-01'),
    ...over,
  } as RespondContact;
}

let lastClient: QueryClient;
function renderSection(c: RespondContact) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  lastClient = client;
  return render(
    <QueryClientProvider client={client}>
      <ContactUserAccountSection contact={c} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  permsRef.view = true;
  permsRef.add = true;
  permsRef.edit = true;
  unlinkPending = null;
  getUsersSelectMock.mockResolvedValue([]);
  updateUserContactLinkMock.mockResolvedValue({});
});

afterEach(() => cleanup());

describe('ContactUserAccountSection - no user yet', () => {
  it('shows "No user yet" with both Create user and Link existing user', () => {
    renderSection(contact());
    expect(screen.getByText('No user yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create user' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Link existing user' })).toBeInTheDocument();
  });

  it('Create user opens the Add user modal with this contact locked', () => {
    renderSection(contact());
    fireEvent.click(screen.getByRole('button', { name: 'Create user' }));
    expect(screen.getByTestId('user-add-dialog-open')).toHaveTextContent(`locked-contact:${CONTACT_ID}`);
  });

  it('hides Create user without users.add', () => {
    permsRef.add = false;
    renderSection(contact());
    expect(screen.queryByRole('button', { name: 'Create user' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Link existing user' })).toBeInTheDocument();
  });

  it('hides Link existing user without users.edit', () => {
    permsRef.edit = false;
    renderSection(contact());
    expect(screen.getByRole('button', { name: 'Create user' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Link existing user' })).not.toBeInTheDocument();
  });

  // Fix round 2, S5: without users.view the API sends no linked user, so "No
  // user yet" would be a false statement for a contact that has one. The
  // section is hidden instead, as the list hides its User column.
  it('without users.view renders no section at all, even for a linked contact', () => {
    permsRef.view = false;
    const { container } = renderSection(contact({ linked_user_id: null, linked_user: null }));
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText('User account')).not.toBeInTheDocument();
    expect(screen.queryByText('No user yet')).not.toBeInTheDocument();
  });

  it('Link existing user lists unlinked active users through getUsersSelect', async () => {
    renderSection(contact());
    fireEvent.click(screen.getByRole('button', { name: 'Link existing user' }));
    await waitFor(() =>
      expect(getUsersSelectMock).toHaveBeenCalledWith({ status: 'ACTIVE', unlinked: true }),
    );
  });

  // Fix round 2, N2: after a link, the picker's unlinked-user list and the
  // linked user's own page are both stale; both are invalidated.
  it('a successful link invalidates the unlinked-user list and that user', async () => {
    getUsersSelectMock.mockResolvedValue([{ id: 'user-bob', name: 'Bob Lee', email: null }]);
    renderSection(contact());
    const invalidate = vi.spyOn(lastClient, 'invalidateQueries');

    fireEvent.click(screen.getByRole('button', { name: 'Link existing user' }));
    fireEvent.click(await screen.findByRole('combobox'));
    fireEvent.click(await screen.findByText('Bob Lee'));
    fireEvent.click(screen.getByRole('button', { name: 'Link' }));

    await waitFor(() => expect(updateUserContactLinkMock).toHaveBeenCalledWith('user-bob', CONTACT_ID));
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['unlinked-users'] }),
    );
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['user-user', 'user-bob'] });
  });
});

describe('ContactUserAccountSection - linked', () => {
  const LINKED = contact({
    linked_user: {
      id: USER_ID,
      name: 'Kia Yee',
      email: 'kia@zzt.test',
      status: 'ACTIVE',
      has_password: true,
      roles: [{ id: 'role-1', name: 'Staff' }],
      phone_differs_from_contact: false,
    },
  });

  it('shows the user link, roles and Signs in by', () => {
    renderSection(LINKED);
    const link = screen.getByRole('link', { name: 'Kia Yee' });
    expect(link).toHaveAttribute('href', `/user-management/users/${USER_ID}`);
    expect(screen.getByText('Staff')).toBeInTheDocument();
    expect(screen.getByText('Email and password, WhatsApp code, Portal link')).toBeInTheDocument();
    expect(screen.queryByText('No user yet')).not.toBeInTheDocument();
  });

  it('shows Unlink for an editor', () => {
    renderSection(LINKED);
    expect(screen.getByRole('button', { name: 'Unlink WhatsApp contact' })).toBeInTheDocument();
    expect(deferredActionInput).toHaveBeenCalledWith(
      expect.objectContaining({ actionKey: 'user.unlink_contact', entityType: 'user', entityId: USER_ID }),
    );
  });

  it('hides Unlink without users.edit', () => {
    permsRef.edit = false;
    renderSection(LINKED);
    expect(screen.queryByRole('button', { name: 'Unlink WhatsApp contact' })).not.toBeInTheDocument();
  });

  it('shows "No roles assigned" when the linked user holds none', () => {
    renderSection(contact({
          linked_user: {
            id: USER_ID,
            name: 'Kia Yee',
            email: 'kia@zzt.test',
            status: 'ACTIVE',
            has_password: false,
            roles: [],
            phone_differs_from_contact: false,
          },
        }));
    expect(screen.getByText('No roles assigned')).toBeInTheDocument();
    expect(screen.getByText('WhatsApp code, Portal link')).toBeInTheDocument();
  });

  // Fix round 2, S3: the WhatsApp code goes to the USER's phone, so it is a
  // way in only while that phone equals the contact's.
  it('leaves out "WhatsApp code" when the user phone differs from the contact (or is empty)', () => {
    renderSection(contact({
          linked_user: {
            id: USER_ID,
            name: 'Kia Yee',
            email: 'kia@zzt.test',
            status: 'ACTIVE',
            has_password: true,
            roles: [],
            phone_differs_from_contact: true,
          },
        }));
    expect(screen.getByText('Email and password, Portal link')).toBeInTheDocument();
    expect(screen.queryByText(/WhatsApp code/)).not.toBeInTheDocument();
  });

  it('never renders the user or contact id as text', () => {
    renderSection(LINKED);
    expect(document.body.textContent ?? '').not.toMatch(UUID_RE);
  });
});
