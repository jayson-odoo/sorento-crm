/**
 * SpecVisibilitySection - the card built in S1 against the mocked service
 * (PLAN-spec-visibility-policy, UAC AC-2..AC-5).
 *
 * Mocked at the SERVICE boundary: the card + hooks are real, `specVisibilityService`
 * is not - which URL/body each function calls is that service's own contract,
 * proven in `services/specVisibilityService.test.ts`.
 *
 * SearchableMultiSelect is stubbed as a deterministic control (the technique
 * `StockVisibilitySection.test.tsx` established) so a pick is a plain fireEvent
 * rather than a Radix popover interaction. `pickers.real` renders the real control
 * for the one assertion that is actually about the shared component (no key slug
 * text in the closed-picker DOM).
 *
 * Because the card itself was fully built in S1 (Phase 1, mocked), most of these
 * are expected to be GREEN already - that is fine (captain's note); they still
 * guard the contract the S2 backend swap must not break.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    custom: vi.fn(),
    message: vi.fn(),
    // The pending-entity store takes its own countdown toast down once the
    // parked removal settles - without this the store's follow-through timer
    // throws an unhandled rejection if it fires after the test ends.
    dismiss: vi.fn(),
  },
}));

const pickers = vi.hoisted(() => ({ real: false }));

vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const Real = actual.SearchableMultiSelect;
  type Props = Parameters<typeof Real>[0];
  const Stub = ({ value, onChange, options, placeholder, disabled }: Props) => {
    const selected = value ?? [];
    return (
      <div
        data-testid="spec-keys-picker"
        data-placeholder={placeholder ?? ''}
        aria-disabled={!!disabled}
      >
        {selected.map((v) => {
          const opt = (options ?? []).find((o) => o.value === v);
          return (
            <span key={v} data-testid="spec-key-chip">
              {opt?.label ?? v}
              <button
                type="button"
                aria-label={`Remove ${opt?.label ?? v}`}
                onClick={() => onChange(selected.filter((x) => x !== v))}
              >
                x
              </button>
            </span>
          );
        })}
        {(options ?? []).map((o) => (
          <button
            key={o.value}
            type="button"
            data-testid="spec-key-option"
            aria-pressed={selected.includes(o.value)}
            onClick={() =>
              onChange(
                selected.includes(o.value)
                  ? selected.filter((v) => v !== o.value)
                  : [...selected, o.value],
              )
            }
          >
            {o.label}
          </button>
        ))}
      </div>
    );
  };
  return {
    ...actual,
    SearchableMultiSelect: (props: Props) => (pickers.real ? <Real {...props} /> : <Stub {...props} />),
  };
});

const service = vi.hoisted(() => ({
  getSpecVisibility: vi.fn(),
  saveSpecVisibility: vi.fn(),
  deleteSpecVisibility: vi.fn(),
  getSpecVisibilityKeys: vi.fn(),
}));

const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pa-1',
  action_key: 'spec_visibility_policy.remove',
  entity_type: 'spec_visibility_policy',
  entity_id: 'contact-77',
  commit_at: '2026-09-13T10:00:05',
  window_seconds: 5,
});
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

vi.mock('@/services/specVisibilityService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/specVisibilityService')>();
  return { ...actual, ...service };
});

import { toast } from '@/lib/toast';
import { pendingEntityStore } from '@/lib/pending-entity-store';
import { SpecVisibilitySection } from './SpecVisibilitySection';
import type {
  SpecKeyRef,
  SpecVisibilityPolicy,
  SpecVisibilityPolicyResponse,
  SpecVisibilityScope,
} from '@/services/specVisibilityService';

const BOARD_THICKNESS: SpecKeyRef = { key: 'board_thickness', label: 'Drainer board / countertop thickness' };
const FINISH: SpecKeyRef = { key: 'finish_colour', label: 'Finish or colour' };
const MATERIAL: SpecKeyRef = { key: 'material', label: 'Material' };
const THICKNESS: SpecKeyRef = { key: 'thickness', label: 'Thickness' };
const KEYS: SpecKeyRef[] = [BOARD_THICKNESS, FINISH, MATERIAL, THICKNESS]; // sorted by label

const CONTACT_SCOPE: SpecVisibilityScope = { kind: 'contact', contactId: 'contact-77' };
const SEGMENT_SCOPE: SpecVisibilityScope = { kind: 'segment', segmentCode: 'retail' };
const DEFAULT_SCOPE: SpecVisibilityScope = { kind: 'default' };

function policy(
  specs: SpecKeyRef[] | null,
  excluded: SpecKeyRef[] | null,
  hidden: SpecKeyRef[],
  source: SpecVisibilityPolicy['source'],
  sourceLabel: string | null = null,
): SpecVisibilityPolicy {
  return { specs, excluded_specs: excluded, hidden, source, source_label: sourceLabel };
}

function respondWith(build: () => SpecVisibilityPolicyResponse) {
  service.getSpecVisibility.mockImplementation(async () => build());
}

function renderSection(scope: SpecVisibilityScope) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <SpecVisibilitySection scope={scope} />
    </QueryClientProvider>,
  );
  return { queryClient, ...utils };
}

async function waitForCard() {
  await waitFor(() => expect(screen.getByTestId('spec-keys-picker')).toBeInTheDocument());
}

function showOnlyRadio(): HTMLElement {
  return screen.getByRole('radio', { name: 'Show only' });
}
function hideTheseRadio(): HTMLElement {
  return screen.getByRole('radio', { name: 'Hide these' });
}

beforeEach(() => {
  pickers.real = false;
  vi.clearAllMocks();
  service.getSpecVisibilityKeys.mockResolvedValue(KEYS);
});

afterEach(() => {
  vi.restoreAllMocks();
  // AC-4's "Remove only with an override" test parks a removal with a
  // `commit_at` in the past, so the store's own follow-through timer is armed
  // for real; putting it down here (rather than waiting for it to fire on its
  // own after the test ends) is what keeps a later suite from seeing an
  // unhandled rejection from a timer this test left running.
  pendingEntityStore.clear('spec_visibility_policy', 'contact-77');
});

describe('AC-2 - the effective policy, where it comes from, and the picker', () => {
  it('shows the source badge, exactly two rule options, a key label (no slug), and Hidden today', async () => {
    pickers.real = true;
    const own = policy(null, [THICKNESS], [THICKNESS], 'contact');
    respondWith(() => ({ effective: own, override: own }));

    renderSection(CONTACT_SCOPE);
    await waitFor(() => expect(screen.getByText('Contact override')).toBeInTheDocument());

    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(2);
    expect(radios.map((r) => r.textContent)).toEqual(['Show only', 'Hide these']);
    expect(screen.getByText('Thickness')).toBeInTheDocument();
    expect(screen.queryByText('thickness')).not.toBeInTheDocument();
    expect(screen.getByText('Hidden today: Thickness')).toBeInTheDocument();
  });

  it('names the market segment by NAME, never the code', async () => {
    const own = policy(null, [], [], 'segment', 'Project');
    respondWith(() => ({ effective: own, override: own }));

    renderSection(SEGMENT_SCOPE);
    await waitForCard();

    expect(screen.getByText('Market segment: Project')).toBeInTheDocument();
    expect(screen.queryByText('project')).not.toBeInTheDocument();
  });

  it('reads Default at the floor of the chain, and "Nothing hidden" when nothing is', async () => {
    const own = policy(null, [], [], 'default');
    respondWith(() => ({ effective: own, override: own }));

    renderSection(DEFAULT_SCOPE);
    await waitForCard();

    expect(screen.getByText('Default')).toBeInTheDocument();
    expect(screen.getByText('Hidden today: Nothing hidden')).toBeInTheDocument();
  });
});

describe('AC-3 - placeholders name the reading in force', () => {
  it('Show only + null reads "All specs"', async () => {
    const own = policy(null, null, [], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    renderSection(CONTACT_SCOPE);
    await waitForCard();
    expect(screen.getByTestId('spec-keys-picker').getAttribute('data-placeholder')).toBe(
      'All specs',
    );
  });

  it('Show only + [] reads "No specs"', async () => {
    const own = policy([], null, KEYS, 'contact');
    respondWith(() => ({ effective: own, override: own }));
    renderSection(CONTACT_SCOPE);
    await waitForCard();
    expect(screen.getByTestId('spec-keys-picker').getAttribute('data-placeholder')).toBe(
      'No specs',
    );
  });

  it('Hide these + [] reads "All specs"', async () => {
    const own = policy(null, [], [], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    renderSection(CONTACT_SCOPE);
    await waitForCard();
    expect(hideTheseRadio()).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('spec-keys-picker').getAttribute('data-placeholder')).toBe(
      'All specs',
    );
  });

  it('flipping Hide these (no chips) to Show only yields null, never []', async () => {
    const own = policy(null, [], [], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    const saved = policy(null, [], [], 'contact');
    service.saveSpecVisibility.mockResolvedValue({ effective: saved, override: saved });

    renderSection(CONTACT_SCOPE);
    await waitForCard();

    fireEvent.click(showOnlyRadio());
    expect(screen.getByTestId('spec-keys-picker').getAttribute('data-placeholder')).toBe(
      'All specs',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Save spec visibility' }));

    await waitFor(() =>
      expect(service.saveSpecVisibility).toHaveBeenCalledWith(CONTACT_SCOPE, {
        spec_keys: null,
        excluded_spec_keys: null,
      }),
    );
  });
});

describe('AC-4 - Save bodies and dirty tracking', () => {
  it('sends {spec_keys: ids, excluded_spec_keys: null} under Show only', async () => {
    const inherited = policy(null, null, [], 'default');
    respondWith(() => ({ effective: inherited, override: null }));
    const saved = policy([MATERIAL], null, [BOARD_THICKNESS, FINISH, THICKNESS], 'contact');
    service.saveSpecVisibility.mockResolvedValue({ effective: saved, override: saved });

    renderSection(CONTACT_SCOPE);
    await waitForCard();

    fireEvent.click(screen.getByRole('button', { name: 'Material' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save spec visibility' }));

    await waitFor(() =>
      expect(service.saveSpecVisibility).toHaveBeenCalledWith(CONTACT_SCOPE, {
        spec_keys: ['material'],
        excluded_spec_keys: null,
      }),
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Spec visibility saved'));
  });

  it('sends {spec_keys: null, excluded_spec_keys: ids} under Hide these', async () => {
    const own = policy(null, [], [], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    const saved = policy(null, [THICKNESS], [THICKNESS], 'contact');
    service.saveSpecVisibility.mockResolvedValue({ effective: saved, override: saved });

    renderSection(CONTACT_SCOPE);
    await waitForCard();

    fireEvent.click(screen.getByRole('button', { name: 'Thickness' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save spec visibility' }));

    await waitFor(() =>
      expect(service.saveSpecVisibility).toHaveBeenCalledWith(CONTACT_SCOPE, {
        spec_keys: null,
        excluded_spec_keys: ['thickness'],
      }),
    );
  });

  it('a rule flip alone enables Save, and flipping back restores clean', async () => {
    const own = policy([MATERIAL], null, [BOARD_THICKNESS, FINISH, THICKNESS], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    renderSection(CONTACT_SCOPE);
    await waitForCard();

    expect(screen.getByRole('button', { name: 'Save spec visibility' })).toBeDisabled();
    fireEvent.click(hideTheseRadio());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save spec visibility' })).toBeEnabled(),
    );
    fireEvent.click(showOnlyRadio());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save spec visibility' })).toBeDisabled(),
    );
  });

  it('toasts the extracted error message when the save is rejected', async () => {
    const own = policy(null, [THICKNESS], [THICKNESS], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    service.saveSpecVisibility.mockRejectedValue(new Error('Unknown spec key: ZZT-GHOST'));

    renderSection(CONTACT_SCOPE);
    await waitForCard();
    fireEvent.click(screen.getByRole('button', { name: 'Material' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save spec visibility' }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Unknown spec key: ZZT-GHOST'),
    );
  });
});

describe('AC-4 - Remove only with an override', () => {
  it('offers no Remove on an inheriting tier', async () => {
    respondWith(() => ({
      effective: policy(null, [THICKNESS], [THICKNESS], 'segment', 'Retail'),
      override: null,
    }));
    renderSection(CONTACT_SCOPE);
    await waitForCard();
    expect(screen.queryByRole('button', { name: /^Remove (override|policy)$/ })).not.toBeInTheDocument();
  });

  it('shows Remove override on a contact with its own row, and parks it with no dialog', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm');
    const own = policy(null, [THICKNESS], [THICKNESS], 'contact');
    respondWith(() => ({ effective: own, override: own }));

    renderSection(CONTACT_SCOPE);
    await waitForCard();
    expect(screen.getByText('Contact override')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Remove override' }));

    await waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionKey: 'spec_visibility_policy.remove',
          entityType: 'spec_visibility_policy',
          entityId: 'contact-77',
        }),
      ),
    );
    expect(service.deleteSpecVisibility).not.toHaveBeenCalled();
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('offers no Remove on the default tier - it is the floor of the chain', async () => {
    const own = policy(null, [THICKNESS, BOARD_THICKNESS], [THICKNESS, BOARD_THICKNESS], 'default');
    respondWith(() => ({ effective: own, override: own }));
    renderSection(DEFAULT_SCOPE);
    await waitForCard();
    expect(screen.queryByRole('button', { name: /^Remove (override|policy)$/ })).not.toBeInTheDocument();
  });
});

describe('AC-5 - loading, error, inherited vs override', () => {
  it('shows a loading skeleton before the policy arrives', () => {
    service.getSpecVisibility.mockReturnValue(new Promise(() => {}));
    renderSection(CONTACT_SCOPE);
    expect(screen.queryByTestId('spec-keys-picker')).not.toBeInTheDocument();
  });

  it('shows the extracted error message on a failed load', async () => {
    service.getSpecVisibility.mockRejectedValue(new Error('Failed to load spec visibility'));
    renderSection(CONTACT_SCOPE);
    await waitFor(
      () => expect(screen.getByText('Failed to load spec visibility')).toBeInTheDocument(),
      { timeout: 3000 },
    );
  });

  it('an inheriting tier names the tier above, and Save is enabled to create the row', async () => {
    respondWith(() => ({
      effective: policy(null, [THICKNESS], [THICKNESS], 'segment', 'Retail'),
      override: null,
    }));
    renderSection(CONTACT_SCOPE);
    await waitForCard();
    expect(screen.getByText('Market segment: Retail')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save spec visibility' })).toBeEnabled();
  });

  it('an override tier shows Contact override, and Save is disabled until dirty', async () => {
    const own = policy(null, [THICKNESS], [THICKNESS], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    renderSection(CONTACT_SCOPE);
    await waitForCard();
    expect(screen.getByText('Contact override')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save spec visibility' })).toBeDisabled();
  });
});
