/**
 * AccessAgentForm — group-level SLA policy picker
 * (PLAN-conversation-policy-binding, D6 / UAC-1, UAC-2, UAC-3, UAC-7).
 *
 * - renders a policy Select per team-set group, listing policies as `name (code)`
 * - loads an existing bound policy from the group's rows
 * - a group with NO policy shows "— No policy —" and save is NOT blocked
 * - on submit the payload stamps the group's policy_id onto EVERY assignment row
 *
 * Radix Select is replaced with a native <select> so policy choice is deterministic
 * in jsdom (no pointer-capture). getSLAPolicies + setAgentTeams are mocked.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Radix (Switch) reads element size via ResizeObserver, absent in jsdom.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

import AccessAgentForm from './AccessAgentForm';

// --- service mocks ---------------------------------------------------------
const getSLAPolicies = vi.fn();
const setAgentTeams = vi.fn();

vi.mock('../services/accessAgentService', () => ({
  setAgentTeams: (...a: unknown[]) => setAgentTeams(...a),
}));
vi.mock('@/app/(protected)/sla-management/sla-policies/services/slaPolicyService', () => ({
  getSLAPolicies: (...a: unknown[]) => getSLAPolicies(...a),
}));

// --- hook mocks ------------------------------------------------------------
const updateMutateAsync = vi.fn().mockResolvedValue({});
const createMutateAsync = vi.fn().mockResolvedValue({});

let agentTeamsAssignments: Array<Record<string, unknown>> = [];
let teamsList: Array<{ id: string; name: string }> = [];

// STABLE references: effects in the component depend on these query results by
// identity. Returning a fresh object/array each render would loop setState forever.
const STABLE_AGENT = {
  id: 'agent-1',
  code: 'AGENT1',
  name: 'Agent 1',
  description: '',
  is_active: true,
  assign_to_new_internal_contacts: false,
};
const STABLE_EMPTY: never[] = [];
const STABLE_NAV = { data: STABLE_EMPTY };

vi.mock('../hooks/useAccessAgents', () => ({
  useAccessAgent: () => ({ data: STABLE_AGENT, isLoading: false }),
  useAccessAgents: () => ({ data: STABLE_NAV }),
  useCreateAccessAgent: () => ({ mutateAsync: createMutateAsync, isPending: false }),
  useUpdateAccessAgent: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
  useAgentTeams: () => ({ data: { assignments: agentTeamsAssignments } }),
  useTeams: () => ({ data: teamsList }),
}));


vi.mock('@/components/common/RecordNavigation', () => ({
  default: () => <div data-testid="record-nav" />,
}));

// Radix Switch's ref-size measurement loops under the jsdom ResizeObserver stub;
// it isn't under test, so render a plain checkbox.
vi.mock('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange }: { checked?: boolean; onCheckedChange?: (v: boolean) => void }) => (
    <input
      type="checkbox"
      role="switch"
      checked={!!checked}
      onChange={(e) => onCheckedChange?.(e.target.checked)}
    />
  ),
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

// --- Radix Select -> native <select> --------------------------------------
// Collect SelectItem descendants into <option>s so value/onValueChange round-trip.
// The component now uses the standard SearchableSelect. Mock it as a native <select> so the
// options are in the DOM without driving a popover — the assertions here are about labels and
// the value that reaches the form, not about popover mechanics.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options = [],
    placeholder,
  }: {
    value?: string;
    onChange?: (v: string) => void;
    options?: Array<{ value: string; label: string; disabled?: boolean }>;
    placeholder?: string;
  }) => (
    <select
      data-testid="native-select"
      aria-label={placeholder}
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const POLICIES = [
  { id: 'pol-std', code: 'STANDARD', name: 'Standard', is_active: true },
  { id: 'pol-fast', code: 'WAREHOUSE_FAST', name: 'Warehouse Fast', is_active: true },
];

function renderForm() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AccessAgentForm accessAgentId="agent-1" />
    </QueryClientProvider>,
  );
}

// The form renders several native <select>s (team, tier, policy). The POLICY
// select only mounts once getSLAPolicies resolves, so waiting on "any select
// exists" races: `.find(...)` could return undefined (masked by `!`) or find the
// select before its value is applied. Wait for the policy select specifically.
async function findPolicySelect(): Promise<HTMLSelectElement> {
  return await waitFor(() => {
    const sel = screen
      .getAllByTestId('native-select')
      .find((s) =>
        Array.from(s.querySelectorAll('option')).some((o) => o.textContent === '— No policy —'),
      );
    expect(sel).toBeTruthy();
    return sel as HTMLSelectElement;
  });
}

describe('AccessAgentForm group SLA policy picker', () => {
  beforeEach(() => {
    getSLAPolicies.mockReset();
    setAgentTeams.mockReset();
    updateMutateAsync.mockClear();
    push.mockReset();
    getSLAPolicies.mockResolvedValue({ data: POLICIES, total: POLICIES.length, page: 1, limit: 100 });
    setAgentTeams.mockResolvedValue({ assignments: [] });
    teamsList = [
      { id: 'team-1', name: 'Team One' },
      { id: 'team-2', name: 'Team Two' },
    ];
    agentTeamsAssignments = [];
  });

  it('renders a policy Select per group listing policies as "name (code)"', async () => {
    agentTeamsAssignments = [
      { code: 'purchasing', team_id: 'team-1', tier: 1, policy_id: null },
    ];
    renderForm();

    // The policy options expose "name (code)" labels.
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'Standard (STANDARD)' })).toBeInTheDocument(),
    );
    expect(screen.getByRole('option', { name: 'Warehouse Fast (WAREHOUSE_FAST)' })).toBeInTheDocument();
    // And the "— No policy —" sentinel option.
    expect(screen.getByRole('option', { name: '— No policy —' })).toBeInTheDocument();
  });

  it('loads an existing bound policy from the group rows', async () => {
    agentTeamsAssignments = [
      { code: 'purchasing', team_id: 'team-1', tier: 1, policy_id: 'pol-fast' },
      { code: 'purchasing', team_id: 'team-2', tier: 2, policy_id: 'pol-fast' },
    ];
    renderForm();

    // The group's policy select reflects the bound policy.
    const policySelect = await findPolicySelect();
    await waitFor(() => expect(policySelect.value).toBe('pol-fast'));
  });

  it('a group with no policy shows "— No policy —" and save is NOT blocked', async () => {
    agentTeamsAssignments = [
      { code: 'general', team_id: 'team-1', tier: 1, policy_id: null },
    ];
    renderForm();

    await waitFor(() => expect(screen.getAllByTestId('native-select').length).toBeGreaterThan(0));
    const policySelect = screen
      .getAllByTestId('native-select')
      .find((s) => Array.from(s.querySelectorAll('option')).some((o) => o.textContent === '— No policy —'))! as HTMLSelectElement;
    // No bound policy -> the "— No policy —" sentinel is selected.
    expect(policySelect.value).toBe('__none__');

    // Save still goes through (unbound is allowed at the FE; D8 fallback on the BE).
    fireEvent.click(screen.getByRole('button', { name: /Update Access Agent/i }));
    await waitFor(() => expect(setAgentTeams).toHaveBeenCalled());
    const [, assignments] = setAgentTeams.mock.calls[0];
    expect(assignments).toHaveLength(1);
    // Unbound group -> policy_id omitted (undefined), never a blocking error.
    expect(assignments[0].policy_id).toBeUndefined();
  });

  it('stamps the group policy_id onto every assignment row of that group on submit', async () => {
    agentTeamsAssignments = [
      { code: 'purchasing', team_id: 'team-1', tier: 1, policy_id: 'pol-std' },
      { code: 'purchasing', team_id: 'team-2', tier: 2, policy_id: 'pol-std' },
    ];
    renderForm();

    // Change the group policy to the WAREHOUSE_FAST profile.
    const policySelect = await findPolicySelect();
    await waitFor(() => expect(policySelect.value).toBe('pol-std'));
    fireEvent.change(policySelect, { target: { value: 'pol-fast' } });

    fireEvent.click(screen.getByRole('button', { name: /Update Access Agent/i }));

    await waitFor(() => expect(setAgentTeams).toHaveBeenCalled());
    const [agentId, assignments] = setAgentTeams.mock.calls[0];
    expect(agentId).toBe('agent-1');
    expect(assignments).toHaveLength(2);
    // The chosen policy is stamped onto BOTH tier rows of the group.
    expect(assignments.every((a: { policy_id?: string }) => a.policy_id === 'pol-fast')).toBe(true);
    expect(assignments.map((a: { tier?: number }) => a.tier).sort()).toEqual([1, 2]);
  });
});
