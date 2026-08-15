/**
 * The one grid both onboarding screens render.
 *
 * What is worth pinning here is the DIFFERENCE between the modes, because the
 * whole reason this is one component is that the requester's view and the
 * reviewer's view must not drift: same columns in the same order, with the
 * reviewer's extra columns added rather than substituted.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { PeopleGrid } from './PeopleGrid';
import type {
  OnboardingPerson,
  OnboardingTemplateOption,
} from './types';

// DataGrid fetches the user's hidden/resized columns and renders skeletons until
// that answers; under jsdom nothing does, so rows never mount without this.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const TEMPLATES: OnboardingTemplateOption[] = [
  {
    id: 'tpl-sales',
    name: 'Salesperson',
    description: 'Sees their own orders.',
    default_needs_system_account: true,
    default_needs_respond_contact: true,
    default_needs_agent_seat: false,
  },
  {
    id: 'tpl-dealer',
    name: 'Dealer',
    description: 'No system login.',
    default_needs_system_account: false,
    default_needs_respond_contact: true,
    default_needs_agent_seat: false,
  },
];

function person(overrides: Partial<OnboardingPerson> = {}): OnboardingPerson {
  return {
    id: 'p1',
    row_number: 1,
    full_name: 'Nurul Aisyah',
    nick_name: 'Aisyah',
    phone_raw: '012-3456781',
    email_raw: 'aisyah@mocha.com.my',
    section_label: 'SALES PERSON',
    template_id: 'tpl-sales',
    requester_note: null,
    reviewer_note: null,
    needs_system_account: true,
    needs_respond_contact: true,
    needs_agent_seat: false,
    review_status: 'proposed',
    rejection_reason: null,
    problems: [],
    collisions: [],
    user_step: 'pending',
    user_error: null,
    user_label: null,
    contact_step: 'pending',
    contact_error: null,
    agent_step: 'pending',
    agent_error: null,
    ...overrides,
  };
}

/**
 * The grid's own card. One rendering at every width now - the parallel
 * small-screen card layout is gone, so a value can only be on screen once.
 */
function grid() {
  return screen.getByTestId('people-grid');
}

/** The template picker for a row: a SearchableSelect behind an sr-only label. */
function templateTrigger() {
  return within(grid()).getAllByLabelText('Access template')[0];
}

describe('PeopleGrid', () => {
  it('renders an empty state rather than an empty table', () => {
    render(
      <PeopleGrid
        mode="intake"
        people={[]}
        templates={TEMPLATES}
        emptyMessage="No people yet. Upload your sheet above."
      />,
    );
    expect(screen.getAllByText(/No people yet/i).length).toBeGreaterThan(0);
  });

  it('renders a loading state', () => {
    const { container } = render(
      <PeopleGrid mode="intake" people={[]} templates={TEMPLATES} isLoading />,
    );
    expect(container.querySelectorAll('[data-slot="skeleton"], .animate-pulse').length)
      .toBeGreaterThan(0);
  });

  it('shows the requester her own values back, raw', () => {
    render(<PeopleGrid mode="intake" people={[person()]} templates={TEMPLATES} />);
    const cells = within(grid());
    expect(cells.getByLabelText('Name, row 1')).toHaveValue('Nurul Aisyah');
    // The dash and the spacing are hers. Normalising what she sees reads as the
    // system losing her input.
    expect(cells.getByLabelText('Phone, row 1')).toHaveValue('012-3456781');
  });

  it('raises a patch when a field is edited, once the field is left', () => {
    const onPatch = vi.fn();
    render(
      <PeopleGrid
        mode="intake"
        people={[person()]}
        templates={TEMPLATES}
        onPatchPerson={onPatch}
      />,
    );
    const email = within(grid()).getByLabelText('Email, row 1');
    fireEvent.change(email, { target: { value: 'new@mocha.com.my' } });
    // An edit is one event, not one per character: the parent hears about it
    // when she moves off the field.
    fireEvent.blur(email);
    expect(onPatch).toHaveBeenCalledWith('p1', { email_raw: 'new@mocha.com.my' });
  });

  it('keeps the caret in the cell while a name is typed, and patches once', () => {
    // The bug this pins: the columns were rebuilt whenever a handler identity
    // changed, which is every keystroke for a parent that owns the rows. New
    // cell renderers meant React remounted the cell, so the input lost focus
    // after the first character and a name could not be typed at all.
    const onPatch = vi.fn();
    const { rerender } = render(
      <PeopleGrid
        mode="intake"
        people={[person({ full_name: '' })]}
        templates={TEMPLATES}
        // Inline, like both real callers: the grid has to survive it.
        onPatchPerson={(id, patch) => onPatch(id, patch)}
      />,
    );

    const name = within(grid()).getByLabelText('Name, row 1') as HTMLInputElement;
    name.focus();
    expect(document.activeElement).toBe(name);

    let typed = '';
    for (const char of 'Aisyah') {
      typed += char;
      fireEvent.change(name, { target: { value: typed } });
      // The controlled parent re-renders on every keystroke it hears about; do
      // the same here so a remount would show up.
      rerender(
        <PeopleGrid
          mode="intake"
          people={[person({ full_name: '' })]}
          templates={TEMPLATES}
          onPatchPerson={(id, patch) => onPatch(id, patch)}
        />,
      );
      expect(document.activeElement).toBe(name);
      expect(name.value).toBe(typed);
    }

    // Nothing was sent while she was still typing.
    expect(onPatch).not.toHaveBeenCalled();

    fireEvent.blur(name);
    expect(onPatch).toHaveBeenCalledTimes(1);
    expect(onPatch).toHaveBeenCalledWith('p1', { full_name: 'Aisyah' });
  });

  it('takes an update from outside into a field nobody is typing into', () => {
    const { rerender } = render(
      <PeopleGrid
        mode="review"
        people={[person({ full_name: 'Nurul Aisyah' })]}
        templates={TEMPLATES}
        onPatchPerson={vi.fn()}
      />,
    );
    expect(within(grid()).getByLabelText('Name, row 1')).toHaveValue('Nurul Aisyah');

    // A refetch (or another reviewer's edit) landing on an idle field must win.
    rerender(
      <PeopleGrid
        mode="review"
        people={[person({ full_name: 'Nurul Aisyah binti Rahman' })]}
        templates={TEMPLATES}
        onPatchPerson={vi.fn()}
      />,
    );
    expect(within(grid()).getByLabelText('Name, row 1')).toHaveValue(
      'Nurul Aisyah binti Rahman',
    );
  });

  it('commits on Enter without waiting for the field to be left', () => {
    const onPatch = vi.fn();
    render(
      <PeopleGrid
        mode="intake"
        people={[person()]}
        templates={TEMPLATES}
        onPatchPerson={onPatch}
      />,
    );
    const nickname = within(grid()).getByLabelText('Nickname, row 1');
    fireEvent.change(nickname, { target: { value: 'Ais' } });
    fireEvent.keyDown(nickname, { key: 'Enter' });
    expect(onPatch).toHaveBeenCalledWith('p1', { nick_name: 'Ais' });
    // And leaving the field afterwards does not send the same edit twice.
    fireEvent.blur(nickname);
    expect(onPatch).toHaveBeenCalledTimes(1);
  });

  it('pre-fills the three needs from the template, without locking them', async () => {
    const onPatch = vi.fn();
    render(
      <PeopleGrid
        mode="intake"
        people={[person()]}
        templates={TEMPLATES}
        onPatchPerson={onPatch}
      />,
    );
    fireEvent.click(templateTrigger());
    fireEvent.click(await screen.findByRole('option', { name: /Dealer/ }));
    expect(onPatch).toHaveBeenCalledWith('p1', {
      template_id: 'tpl-dealer',
      needs_system_account: false,
      needs_respond_contact: true,
      needs_agent_seat: false,
    });
  });

  it('is a searchable select, not a raw dropdown', () => {
    render(<PeopleGrid mode="intake" people={[person()]} templates={TEMPLATES} />);
    // Every dropdown-select in this codebase is SearchableSelect, which exposes
    // the combobox role a raw <select> in a cell never did.
    expect(templateTrigger()).toHaveAttribute('role', 'combobox');
  });

  it('offers a way to clear the template', () => {
    const onPatch = vi.fn();
    render(
      <PeopleGrid
        mode="intake"
        people={[person()]}
        templates={TEMPLATES}
        onPatchPerson={onPatch}
      />,
    );
    // An optional select the user can change but never unset is the ADR's named
    // failure; `clearable` is what makes it clearable.
    const clear = within(templateTrigger()).getByRole('button', { name: 'Clear selection' });
    fireEvent.pointerDown(clear);
    expect(onPatch).toHaveBeenCalledWith('p1', { template_id: null });
  });

  it('shows per-row problems as chips', () => {
    render(
      <PeopleGrid
        mode="intake"
        people={[person({ problems: ['no email', 'phone not recognised'] })]}
        templates={TEMPLATES}
      />,
    );
    expect(screen.getAllByText('no email').length).toBeGreaterThan(0);
    expect(screen.getAllByText('phone not recognised').length).toBeGreaterThan(0);
  });

  it('hides collisions and verdicts from the requester', () => {
    render(
      <PeopleGrid
        mode="intake"
        people={[person({ collisions: [{ kind: 'user_email', label: 'Already a user: X' }] })]}
        templates={TEMPLATES}
      />,
    );
    expect(screen.queryByText('Already exists')).not.toBeInTheDocument();
    expect(screen.queryByText('Already a user: X')).not.toBeInTheDocument();
  });

  it('shows collisions and the lane ledger to the reviewer', () => {
    render(
      <PeopleGrid
        mode="review"
        people={[
          person({
            collisions: [{ kind: 'user_email', label: 'Already a user: Tan Wei Ming' }],
            user_step: 'skipped',
          }),
        ]}
        templates={TEMPLATES}
      />,
    );
    expect(screen.getAllByText('Already a user: Tan Wei Ming').length).toBeGreaterThan(0);
    expect(screen.getAllByText('System account').length).toBeGreaterThan(0);
    expect(screen.getAllByText('WhatsApp contact').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Chat-agent seat').length).toBeGreaterThan(0);
  });

  it('labels a pending contact lane as not yet automated rather than in progress', () => {
    render(
      <PeopleGrid mode="review" people={[person()]} templates={TEMPLATES} />,
    );
    expect(screen.getAllByText('Not yet automated').length).toBeGreaterThan(0);
  });

  it('surfaces a failed lane with its reason', () => {
    render(
      <PeopleGrid
        mode="review"
        people={[person({ user_step: 'failed', user_error: 'Email already registered.' })]}
        templates={TEMPLATES}
      />,
    );
    expect(screen.getAllByText('Email already registered.').length).toBeGreaterThan(0);
  });

  it('offers approve and reject per row in review, in the same words as the badge', () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(
      <PeopleGrid
        mode="review"
        people={[person()]}
        templates={TEMPLATES}
        onApprovePerson={onApprove}
        onRejectPerson={onReject}
      />,
    );
    // "Approve", not "Keep": the badge for an approved row already says
    // Approved, and one verdict must not have two names.
    fireEvent.click(within(grid()).getByRole('button', { name: 'Approve' }));
    fireEvent.click(within(grid()).getByRole('button', { name: 'Reject' }));
    expect(onApprove).toHaveBeenCalledWith('p1');
    expect(onReject).toHaveBeenCalledWith('p1');
  });

  it('shows a rejection reason on the row that carries it', () => {
    render(
      <PeopleGrid
        mode="review"
        people={[
          person({ review_status: 'rejected', rejection_reason: 'Left the company.' }),
        ]}
        templates={TEMPLATES}
      />,
    );
    expect(screen.getAllByText('Rejected').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Left the company.').length).toBeGreaterThan(0);
  });

  it('is read-only in readonly mode, with the same values on screen', () => {
    render(<PeopleGrid mode="readonly" people={[person()]} templates={TEMPLATES} />);
    const cells = within(grid());
    expect(cells.queryByLabelText('Name, row 1')).not.toBeInTheDocument();
    expect(cells.getAllByText('Nurul Aisyah').length).toBeGreaterThan(0);
    expect(cells.getAllByText('012-3456781').length).toBeGreaterThan(0);
  });

  it('titles the card it is, so it needs no outer section around it', () => {
    render(
      <PeopleGrid
        mode="intake"
        people={[person()]}
        templates={TEMPLATES}
        title="Access"
        description="Submitted 1"
        actions={<button type="button">Add a person</button>}
      />,
    );
    const card = within(grid());
    expect(card.getByText('Access')).toBeInTheDocument();
    expect(card.getByText('Submitted 1')).toBeInTheDocument();
    expect(card.getByRole('button', { name: 'Add a person' })).toBeInTheDocument();
  });

  it('confirms before a row is removed', async () => {
    const onRemove = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PeopleGrid
          mode="intake"
          people={[person()]}
          templates={TEMPLATES}
          onRemovePerson={onRemove}
        />
      </QueryClientProvider>,
    );

    fireEvent.click(within(grid()).getByRole('button', { name: 'Remove' }));
    // Removing a row throws away what she typed, so it is confirmed in the
    // standard words rather than being one click.
    expect(await screen.findByText('Confirm delete')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Remove Nurul Aisyah from this request? This action cannot be undone.',
      ),
    ).toBeInTheDocument();
    expect(onRemove).not.toHaveBeenCalled();

    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(onRemove).toHaveBeenCalledWith('p1'));
  });
});
