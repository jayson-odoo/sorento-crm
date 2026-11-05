import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PromptDetail } from './PromptDetail';
import type {
  PromptKeySummary,
  PromptVersionDetail,
  PromptVersionsResponse,
} from '../../services/aiPromptsService';

const usePromptVersions = vi.fn();
const usePromptKeys = vi.fn();
const usePromptVersion = vi.fn();
const useSaveVersion = vi.fn();
const useSetLabel = vi.fn();
const useDryRun = vi.fn();
const useHasPermission = vi.fn();
const useRegistryVariables = vi.fn();
const usePromptArchitecture = vi.fn();

vi.mock('../../hooks/useAIAssistantPrompts', () => ({
  usePromptVersions: () => usePromptVersions(),
  usePromptVersion: () => usePromptVersion(),
  useSaveVersion: () => useSaveVersion(),
  useSetLabel: () => useSetLabel(),
  useDryRun: () => useDryRun(),
  // The key list is read twice on this screen: by the "Runs on" card for the agent's
  // model, and here for `dry_runnable`, which is a property of the KEY and is absent
  // from the versions response.
  usePromptKeys: () => usePromptKeys(),
  useSetAgentModel: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRegistryVariables: () => useRegistryVariables(),
  usePromptArchitecture: (...args: unknown[]) => usePromptArchitecture(...args),
  promptsPagerQuery: { listQueryKey: () => ['ai-prompts', 'list'], fetchPage: vi.fn() },
}));
vi.mock('next/navigation', () => ({
  usePathname: () => '/system-management/ai-assistant/prompts/router',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams('page=1&limit=50&sort=name&dir=asc'),
}));
// The pager's own walk is pinned in useListPager's tests; here it only has to be THERE, in the
// record header, pointed at this prompt - and still there after an action.
vi.mock('@/components/common/ListPager', () => ({
  default: ({ currentId, detailPath }: { currentId: string; detailPath: string }) => (
    <div data-testid="list-pager" data-current={currentId} data-path={detailPath} />
  ),
}));
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => useHasPermission(),
}));
// Container pulls SettingsProvider context we don't need in a unit test.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const META: PromptVersionsResponse = {
  name: 'router',
  role: 'Intent / routing',
  active: true,
  activates_in: null,
  variables: ['current_date'],
  labels: { production: 2, staging: null },
  versions: [
    { id: 'router-2', version: 2, commit_message: 'v2', created_by_name: 'Jay', created_at: '2026-07-03T09:00:00', labels: ['production'] },
    { id: 'router-1', version: 1, commit_message: 'seed', created_by_name: 'Seed', created_at: '2026-07-02T09:00:00', labels: [] },
  ],
};

const BASE: PromptVersionDetail = {
  id: 'router-2',
  name: 'router',
  version: 2,
  template: 'Classify {{current_date}}.',
  variables: ['current_date'],
  commit_message: 'v2',
  created_by_name: 'Jay',
  created_at: '2026-07-03T09:00:00',
  labels: ['production'],
};

/** The key list row for `router`, as the prompts list serves it. */
const KEY_ROW: PromptKeySummary = {
  name: 'router',
  role: 'Intent / routing',
  active: true,
  activates_in: null,
  variables: ['current_date'],
  dry_runnable: true,
  production_version: 2,
  staging_version: null,
  latest_version: 2,
  updated_at: '2026-07-03T09:00:00',
  updated_by_name: 'Jay',
  provider: null,
  model: null,
};

const saveMutate = vi.fn();
const labelMutate = vi.fn();

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PromptDetail name="router" />
    </QueryClientProvider>,
  );
}

/** The record header's Edit: the editor is read-only until it is pressed (standard form view). */
const startEdit = () => fireEvent.click(screen.getByTestId('edit-prompt'));
/** Radix tabs activate on mousedown. */
const openTab = (name: string) => fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0 });
/** Radix menus open on pointerdown. */
const openMenu = (el: Element) => fireEvent.pointerDown(el, { button: 0, ctrlKey: false, pointerType: 'mouse' });

beforeEach(() => {
  [
    usePromptVersions,
    usePromptVersion,
    usePromptKeys,
    useSaveVersion,
    useSetLabel,
    useDryRun,
    useHasPermission,
  ].forEach((m) => m.mockReset());
  saveMutate.mockReset();
  labelMutate.mockReset();
  useHasPermission.mockReturnValue(true);
  usePromptVersions.mockReturnValue({ data: META, isLoading: false, isError: false });
  usePromptKeys.mockReturnValue({ data: [KEY_ROW], isLoading: false, isError: false });
  usePromptVersion.mockReturnValue({ data: BASE, isLoading: false, isError: false });
  useSaveVersion.mockReturnValue({ mutate: saveMutate, isPending: false });
  useSetLabel.mockReturnValue({ mutate: labelMutate, isPending: false });
  useDryRun.mockReturnValue({ mutate: vi.fn(), isPending: false, data: undefined, isError: false });
  useRegistryVariables.mockReset().mockReturnValue({ data: [], isLoading: false, isError: false });
  usePromptArchitecture.mockReset().mockReturnValue({ data: undefined, isLoading: true, isError: false });
});
afterEach(() => cleanup());

describe('PromptDetail', () => {
  it('loads the production version into the editor by default', () => {
    renderDetail();
    const editor = screen.getByTestId('prompt-editor') as HTMLTextAreaElement;
    expect(editor.value).toBe('Classify {{current_date}}.');
  });

  it('shows a green chip for a present declared var', () => {
    renderDetail();
    const chip = screen.getByTestId('var-chip-current_date');
    expect(chip.getAttribute('data-state')).toBe('present');
  });

  it('hard-blocks save when an unknown token is present', () => {
    renderDetail();
    startEdit();
    const editor = screen.getByTestId('prompt-editor');
    fireEvent.change(editor, { target: { value: 'Classify {{current_date}} and {{bogus}}' } });
    fireEvent.change(screen.getByTestId('commit-message'), { target: { value: 'msg' } });
    expect(screen.getByTestId('var-unknown-error')).toBeInTheDocument();
    expect(screen.getByTestId('save-version')).toBeDisabled();
  });

  it('soft-warns (does not block) when a declared var is removed', () => {
    renderDetail();
    startEdit();
    fireEvent.change(screen.getByTestId('prompt-editor'), { target: { value: 'Classify without the var.' } });
    fireEvent.change(screen.getByTestId('commit-message'), { target: { value: 'msg' } });
    expect(screen.getByTestId('var-missing-warning')).toBeInTheDocument();
    expect(screen.getByTestId('save-version')).not.toBeDisabled();
  });

  it('keeps save disabled until there is a commit message', () => {
    renderDetail();
    startEdit();
    fireEvent.change(screen.getByTestId('prompt-editor'), { target: { value: 'Classify {{current_date}} edited.' } });
    expect(screen.getByTestId('save-version')).toBeDisabled();
    fireEvent.change(screen.getByTestId('commit-message'), { target: { value: 'msg' } });
    expect(screen.getByTestId('save-version')).not.toBeDisabled();
  });

  it('opens the publish confirm dialog for a non-production version', async () => {
    renderDetail();
    openTab('Versions');
    openMenu(screen.getByRole('button', { name: 'Actions for v1' }));
    fireEvent.click(await screen.findByTestId('publish-production-1'));
    expect(screen.getByText('Publish router v1 to production?')).toBeInTheDocument();
    expect(screen.getByText(/changes the live assistant immediately/i)).toBeInTheDocument();
  });

  it('offers the dry-run for an active key that the assistant turn actually reads', () => {
    renderDetail();
    openTab('Dry run');
    expect(screen.getByTestId('dry-run-input')).toBeInTheDocument();
    expect(screen.queryByTestId('dry-run-disabled')).not.toBeInTheDocument();
  });

  it('disables the dry-run for a key outside the assistant pipeline, and says why', () => {
    usePromptKeys.mockReturnValue({
      data: [{ ...KEY_ROW, dry_runnable: false }],
      isLoading: false,
      isError: false,
    });
    renderDetail();
    openTab('Dry run');
    expect(screen.queryByTestId('dry-run-input')).not.toBeInTheDocument();
    expect(screen.getByTestId('dry-run-disabled')).toHaveTextContent(
      /not part of the assistant pipeline/i,
    );
  });

  it('keeps the dormant reason when a dormant key is also not dry-runnable', () => {
    usePromptVersions.mockReturnValue({
      data: { ...META, active: false, activates_in: 'M2.5' },
      isLoading: false,
      isError: false,
    });
    usePromptKeys.mockReturnValue({
      data: [{ ...KEY_ROW, active: false, dry_runnable: false }],
      isLoading: false,
      isError: false,
    });
    renderDetail();
    openTab('Dry run');
    expect(screen.getByTestId('dry-run-disabled')).toHaveTextContent(/Dormant key/i);
  });

  it('leaves the dry-run offered while the key list is still loading', () => {
    usePromptKeys.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    renderDetail();
    openTab('Dry run');
    expect(screen.getByTestId('dry-run-input')).toBeInTheDocument();
  });

  it('shows an AlertDialog (not window.confirm) when switching versions with unsaved edits', () => {
    const confirmSpy = vi.spyOn(window, 'confirm');
    renderDetail();
    startEdit();
    // make the editor dirty
    fireEvent.change(screen.getByTestId('prompt-editor'), { target: { value: 'Classify {{current_date}} edited.' } });
    // click the other version row to switch
    openTab('Versions');
    fireEvent.click(within(screen.getByTestId('version-row-1')).getByText('seed'));
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(screen.getByText(/Discard unsaved edits\?/i)).toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  // ---------------------------------------------------------------------
  // Slice E: a key with no saved version opened an EMPTY editor - the
  // `useEffect` that seeds `draft` only fired off `baseQuery.data.template`,
  // which never arrives when there is nothing to load a version FROM.
  // `fallback_text` (the code default `PROMPT_KEYS[name].fallback()`) is
  // what the editor seeds from instead.
  // ---------------------------------------------------------------------

  it('seeds the draft from fallback_text when the key has no saved version', () => {
    usePromptVersions.mockReturnValue({
      data: {
        ...META,
        labels: { production: null, staging: null },
        versions: [],
        fallback_text: 'RULE TEXT',
      },
      isLoading: false,
      isError: false,
    });
    usePromptVersion.mockReturnValue({ data: undefined, isLoading: false, isError: false });

    renderDetail();

    const editor = screen.getByTestId('prompt-editor') as HTMLTextAreaElement;
    expect(editor.value).toBe('RULE TEXT');
    // Browser re-check: `baseVersion` never resolves with no saved version,
    // so "(base: v{baseVersion})" would have printed "(base: vnull)".
    expect(screen.getByText(/\(base: code default\)/)).toBeInTheDocument();
  });

  it('loads the saved version template, not fallback_text, when a version exists', () => {
    usePromptVersions.mockReturnValue({
      data: { ...META, fallback_text: 'RULE TEXT (should not show)' },
      isLoading: false,
      isError: false,
    });
    // usePromptVersion already returns BASE (template 'Classify {{current_date}}.')
    // from the shared beforeEach.

    renderDetail();

    const editor = screen.getByTestId('prompt-editor') as HTMLTextAreaElement;
    expect(editor.value).toBe('Classify {{current_date}}.');
  });
});

describe('PromptDetail with registry variables (PROMPT-DYNAMIC R5a)', () => {
  const REG_META: PromptVersionsResponse = {
    ...META,
    name: 'chatbot_semantic_parser',
    registry_variables: ['domains', 'statuses'],
  };
  const REG_BASE: PromptVersionDetail = { ...BASE, template: 'ONE of: {{domains}} | null {{current_date}}' };
  const REG_ROWS = [
    { name: 'domains', label: 'Domains', source: 'Chatbot Domains', href: '/system-management/chatbot-domains', count: 3, last_changed: null, rendered: 'order | sales | inventory', used: true },
    { name: 'statuses', label: 'Status words', source: 'Chatbot Status Words', href: '/system-management/chatbot-status-words', count: 8, last_changed: null, rendered: 'S', used: false },
  ];

  beforeEach(() => {
    usePromptVersions.mockReturnValue({ data: REG_META, isLoading: false, isError: false });
    usePromptVersion.mockReturnValue({ data: REG_BASE, isLoading: false, isError: false });
    useRegistryVariables.mockReturnValue({ data: REG_ROWS, isLoading: false, isError: false });
  });

  it('edits in the chip editor, not the plain textarea', () => {
    renderDetail();
    expect(screen.queryByTestId('prompt-editor')).toBeNull();
    const chipEditor = screen.getByTestId('prompt-chip-editor');
    expect(chipEditor.querySelector('[data-chip="domains"]')).not.toBeNull();
  });

  it('shows the wired panel', () => {
    renderDetail();
    expect(screen.getByTestId('wired-row-domains')).toHaveTextContent('In wording');
    expect(screen.getByTestId('wired-row-statuses')).toHaveTextContent('not in wording');
  });

  it('registry tokens never block saving', () => {
    renderDetail();
    expect(screen.queryByTestId('var-unknown-error')).toBeNull();
  });

  it('Preview rendered prompt shows the text the model receives, read-only', () => {
    renderDetail();
    // Radix tabs activate on mousedown (the repo's own convention, e.g. SalesTeamDetail.test.tsx).
    fireEvent.mouseDown(screen.getByTestId('editor-mode-preview'), { button: 0 });
    const preview = screen.getByTestId('prompt-preview');
    expect(preview.textContent).toContain('ONE of: order | sales | inventory | null');
    expect(preview.textContent).not.toContain('{{domains}}');
    // The editor stays mounted but hidden, so the caret survives (hand test #1405, item 2).
    expect(screen.getByTestId('chip-editor-pane')).not.toBeVisible();
    fireEvent.mouseDown(screen.getByTestId('editor-mode-edit'), { button: 0 });
    expect(screen.getByTestId('chip-editor-pane')).toBeVisible();
  });
});

describe('PromptDetail editor mode uses the Tabs primitive (reviewer pass 2)', () => {
  it('Edit and Preview are tabs', () => {
    usePromptVersions.mockReturnValue({ data: { ...META, name: 'chatbot_semantic_parser', registry_variables: ['domains'] }, isLoading: false, isError: false });
    usePromptVersion.mockReturnValue({ data: { ...BASE, template: 'x {{domains}}' }, isLoading: false, isError: false });
    useRegistryVariables.mockReturnValue({ data: [], isLoading: false, isError: false });
    renderDetail();
    const edit = screen.getByTestId('editor-mode-edit');
    const preview = screen.getByTestId('editor-mode-preview');
    expect(edit.getAttribute('role')).toBe('tab');
    expect(edit.getAttribute('data-slot')).toBe('tabs-trigger');
    expect(preview.getAttribute('aria-selected')).toBe('false');
  });
});

describe('PromptDetail wired-panel insert (owner hand test #1405, item 2)', () => {
  it('inserts at the caret in the editor, not at the bottom', () => {
    usePromptVersions.mockReturnValue({ data: { ...META, name: 'chatbot_semantic_parser', registry_variables: ['domains', 'statuses'] }, isLoading: false, isError: false });
    usePromptVersion.mockReturnValue({ data: { ...BASE, template: 'domain_hint = ONE of: | null\nEND' }, isLoading: false, isError: false });
    useRegistryVariables.mockReturnValue({
      data: [{ name: 'domains', label: 'Domains', source: 'Chatbot Domains', href: '/x', count: 3, last_changed: null, rendered: 'a | b', used: false }],
      isLoading: false,
      isError: false,
    });
    renderDetail();
    startEdit();
    const editor = screen.getByTestId('prompt-chip-editor');
    const textNode = editor.firstChild as Text;
    const range = document.createRange();
    range.setStart(textNode, 'domain_hint = ONE of:'.length);
    range.collapse(true);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    fireEvent.mouseUp(editor);
    window.getSelection()!.removeAllRanges();
    fireEvent.click(screen.getByTestId('wired-insert-domains'));
    const chip = editor.querySelector('[data-chip="domains"]')!;
    expect(chip).not.toBeNull();
    expect(chip.previousSibling!.textContent!.endsWith('domain_hint = ONE of:')).toBe(true);
    expect(editor.lastChild!.textContent!.endsWith('END')).toBe(true);
  });
});

// ---------------------------------------------------------------------
// PROMPT-EDITOR-FULLSCREEN (owner, 16 Oct: "let me full screen, otherwise
// this small quite hard to see"). The Editor card goes over the whole window
// through the dealer-kit FocusShell; the editor must NOT remount on the
// toggle, or the caret, the scroll and an open Find are lost.
// ---------------------------------------------------------------------

describe('PromptDetail full screen editor (PROMPT-EDITOR-FULLSCREEN)', () => {
  const overlay = () => document.querySelector('[data-dk-focus-mode]');
  const enter = () => fireEvent.click(screen.getByRole('button', { name: 'Full screen editor' }));

  it('puts the editor card over the window and keeps the unsaved text and the same editor node', () => {
    renderDetail();
    startEdit();
    const editor = screen.getByTestId('prompt-editor') as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: 'Classify {{current_date}} edited.' } });
    editor.scrollTop = 120;
    expect(overlay()).toBeNull();

    enter();

    expect(overlay()).not.toBeNull();
    expect(overlay()!.contains(editor)).toBe(true);
    // Same element: nothing remounted, so caret and scroll are untouched.
    expect(screen.getByTestId('prompt-editor')).toBe(editor);
    expect(editor.value).toBe('Classify {{current_date}} edited.');
    expect(editor.scrollTop).toBe(120);
    // Save stays reachable inside the overlay.
    expect(overlay()!.contains(screen.getByTestId('save-version'))).toBe(true);
    expect(overlay()!.contains(screen.getByTestId('diff-toggle'))).toBe(true);
  });

  it('Exit full screen and Esc both leave, and the text survives', () => {
    renderDetail();
    startEdit();
    const editor = screen.getByTestId('prompt-editor') as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: 'edited once' } });
    enter();
    fireEvent.click(screen.getByRole('button', { name: 'Exit full screen editor' }));
    expect(overlay()).toBeNull();
    expect(screen.getByTestId('prompt-editor')).toBe(editor);

    enter();
    fireEvent.keyDown(editor, { key: 'Escape' });
    expect(overlay()).toBeNull();
    expect((screen.getByTestId('prompt-editor') as HTMLTextAreaElement).value).toBe('edited once');
    expect(screen.getByTestId('prompt-editor')).toBe(editor);
  });

  it('offers Stage / Publish for the loaded version while in full screen', () => {
    renderDetail();
    enter();
    // v2 is already production, so only Stage is offered for it.
    expect(screen.queryByTestId('fullscreen-publish-production')).toBeNull();
    fireEvent.click(screen.getByTestId('fullscreen-publish-staging'));
    expect(screen.getByText('Publish router v2 to staging?')).toBeInTheDocument();
  });

  it('offers Save, not Stage / Publish, in full screen during an edit session', () => {
    renderDetail();
    startEdit();
    enter();
    fireEvent.change(screen.getByTestId('prompt-editor'), { target: { value: 'unsaved' } });
    // Publishing acts on the SAVED version, so beside unsaved text it would mislead; an edit
    // session offers one intent, Save (the record header's rule, carried into full screen).
    expect(screen.queryByTestId('fullscreen-publish-staging')).toBeNull();
    expect(overlay()!.contains(screen.getByTestId('save-version'))).toBe(true);
  });

  describe('with registry variables (chip editor)', () => {
    beforeEach(() => {
      usePromptVersions.mockReturnValue({
        data: { ...META, name: 'chatbot_semantic_parser', registry_variables: ['domains'] },
        isLoading: false,
        isError: false,
      });
      usePromptVersion.mockReturnValue({
        data: { ...BASE, template: 'RULES:\ncurrent one {{domains}}\n# Output\ncurrent two\n== PRICE TERMS (decisive) ==\nlower case line' },
        isLoading: false,
        isError: false,
      });
      useRegistryVariables.mockReturnValue({
        data: [{ name: 'domains', label: 'Domains', source: 'Chatbot Domains', href: '/x', count: 3, last_changed: null, rendered: 'a | b', used: true }],
        isLoading: false,
        isError: false,
      });
    });

    it('Find works in full screen, and Esc closes Find without leaving full screen', () => {
      renderDetail();
      const editor = screen.getByTestId('prompt-chip-editor');
      enter();
      expect(screen.getByTestId('prompt-chip-editor')).toBe(editor);
      fireEvent.click(screen.getByTestId('open-find'));
      fireEvent.change(screen.getByTestId('find-input'), { target: { value: 'current' } });
      expect(screen.getByTestId('find-count')).toHaveTextContent('1/2');
      fireEvent.keyDown(screen.getByTestId('find-input'), { key: 'Enter' });
      expect(screen.getByTestId('find-count')).toHaveTextContent('2/2');
      expect(overlay()!.contains(screen.getByTestId('find-bar'))).toBe(true);

      // Esc on the editor while Find is open closes Find only, and keeps the place the jump
      // scrolled to: a plain focus() sends a contentEditable back to the top.
      const focusSpy = vi.spyOn(editor, 'focus');
      fireEvent.keyDown(editor, { key: 'Escape' });
      expect(focusSpy).toHaveBeenCalledWith({ preventScroll: true });
      expect(screen.queryByTestId('find-bar')).toBeNull();
      expect(overlay()).not.toBeNull();
      // A second Esc leaves full screen.
      fireEvent.keyDown(editor, { key: 'Escape' });
      expect(overlay()).toBeNull();
    });

    it('Preview rendered prompt also shows in full screen, with section headers marked', () => {
      renderDetail();
      enter();
      fireEvent.mouseDown(screen.getByTestId('editor-mode-preview'), { button: 0 });
      const preview = screen.getByTestId('prompt-preview');
      expect(overlay()!.contains(preview)).toBe(true);
      const headings = Array.from(preview.querySelectorAll('[data-heading]')).map((n) => n.textContent);
      expect(headings).toEqual(['RULES:', '# Output', '== PRICE TERMS (decisive) ==']);
      expect(preview.textContent).toContain('current one a | b');
    });
  });
});

describe('PromptDetail Architecture tab (CHAT-INDEX-VIZ FE-2)', () => {
  function renderFor(name: string, registry: string[]) {
    usePromptVersions.mockReturnValue({
      data: { ...META, name, registry_variables: registry },
      isLoading: false,
      isError: false,
    });
    usePromptVersion.mockReturnValue({ data: { ...BASE, name }, isLoading: false, isError: false });
    useRegistryVariables.mockReturnValue({ data: [], isLoading: false, isError: false });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={client}>
        <PromptDetail name={name} />
      </QueryClientProvider>,
    );
  }

  it('shows the Architecture tab for the semantic parser only', () => {
    renderFor('chatbot_semantic_parser', ['domains']);
    expect(screen.getByTestId('editor-mode-architecture')).toHaveTextContent('Architecture');
  });

  it('hides the Architecture tab for any other key, registry variables or not', () => {
    renderFor('chatbot_clarifier', ['domains']);
    expect(screen.queryByTestId('editor-mode-architecture')).toBeNull();
    cleanup();
    renderFor('router', []);
    expect(screen.queryByTestId('editor-mode-architecture')).toBeNull();
  });

  it('opens the architecture view for the shown version and keeps the chip editor mounted but hidden', () => {
    usePromptArchitecture.mockReturnValue({
      data: {
        version: 2, mode: 'block', uses_closed_lists: false, total_size: 10,
        groups: [{ name: 'Rules', size: 10, share: 1 }], lists: [],
      },
      isLoading: false,
      isError: false,
    });
    renderFor('chatbot_semantic_parser', ['domains']);
    fireEvent.mouseDown(screen.getByTestId('editor-mode-architecture'), { button: 0 });
    expect(screen.getByTestId('prompt-architecture')).toBeInTheDocument();
    expect(screen.getByTestId('chip-editor-pane')).toBeInTheDocument();
    expect(screen.getByTestId('chip-editor-pane').hidden).toBe(true);
    const lastCall = usePromptArchitecture.mock.calls.at(-1)!;
    expect(lastCall[0]).toBe('chatbot_semantic_parser');
    expect(lastCall[1]).toBe(2);
  });

  it('hides the variable chips while the Architecture tab is selected and brings them back on Edit', () => {
    usePromptArchitecture.mockReturnValue({
      data: { version: 2, mode: 'block', uses_closed_lists: false, total_size: 10, groups: [{ name: 'Rules', size: 10, share: 1 }], lists: [] },
      isLoading: false,
      isError: false,
    });
    renderFor('chatbot_semantic_parser', ['domains']);
    expect(screen.getByTestId('var-chips')).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByTestId('editor-mode-architecture'), { button: 0 });
    expect(screen.queryByTestId('var-chips')).toBeNull();
    fireEvent.mouseDown(screen.getByTestId('editor-mode-edit'), { button: 0 });
    expect(screen.getByTestId('var-chips')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------
// AI-PROMPTS-STD-VIEWS (owner, 5 Nov): the prompt page is a standard record page - record
// header with the pager, the gear and ONE primary button; line tabs; View -> Edit -> Save.
// ---------------------------------------------------------------------

describe('PromptDetail on the standard record layout (AI-PROMPTS-STD-VIEWS)', () => {
  it('carries the prev/next pager in the record header, pointed at this prompt', () => {
    renderDetail();
    const pager = screen.getByTestId('list-pager');
    expect(pager).toHaveAttribute('data-current', 'router');
    expect(pager).toHaveAttribute('data-path', '/system-management/ai-assistant/prompts');
  });

  it('has a Back to the list that keeps the list state', () => {
    renderDetail();
    const back = screen.getByRole('link', { name: /Back to prompts/i });
    expect(back.getAttribute('href')).toMatch(/^\/system-management\/ai-assistant\/prompts\?/);
    expect(back.getAttribute('href')).toMatch(/page=1/);
  });

  it('lays the record out in line tabs: Prompt, Versions, Model, Dry run', () => {
    renderDetail();
    const tabs = screen.getAllByRole('tab').map((t) => t.textContent?.trim());
    expect(tabs.slice(0, 4)).toEqual(['Prompt', 'Versions', 'Model', 'Dry run']);
  });

  it('shows the role as a field, not a subtitle line', () => {
    renderDetail();
    expect(screen.getByTestId('prompt-role')).toHaveTextContent('Intent / routing');
  });

  it('opens read-only; Edit makes the editor editable and swaps the header to Cancel + Save', () => {
    renderDetail();
    expect(screen.getByTestId('prompt-editor')).toBeDisabled();
    expect(screen.queryByTestId('save-version')).toBeNull();
    expect(screen.queryByTestId('commit-message')).toBeNull();
    startEdit();
    expect(screen.getByTestId('prompt-editor')).not.toBeDisabled();
    expect(screen.getByTestId('save-version')).toBeInTheDocument();
    expect(screen.getByTestId('cancel-edit')).toBeInTheDocument();
    expect(screen.queryByTestId('edit-prompt')).toBeNull();
  });

  it('offers no Edit to a read-only user', () => {
    useHasPermission.mockReturnValue(false);
    renderDetail();
    expect(screen.queryByTestId('edit-prompt')).toBeNull();
  });

  it('Cancel throws the draft away and returns to the stored version', () => {
    renderDetail();
    startEdit();
    fireEvent.change(screen.getByTestId('prompt-editor'), { target: { value: 'scribble' } });
    fireEvent.click(screen.getByTestId('cancel-edit'));
    expect((screen.getByTestId('prompt-editor') as HTMLTextAreaElement).value).toBe('Classify {{current_date}}.');
    expect(screen.getByTestId('prompt-editor')).toBeDisabled();
  });

  it('Save writes a NEW immutable version with the commit message, then leaves edit with the pager back', () => {
    renderDetail();
    startEdit();
    fireEvent.change(screen.getByTestId('prompt-editor'), { target: { value: 'Classify {{current_date}} v3.' } });
    fireEvent.change(screen.getByTestId('commit-message'), { target: { value: 'tighten' } });
    fireEvent.click(screen.getByTestId('save-version'));
    expect(saveMutate).toHaveBeenCalledTimes(1);
    expect(saveMutate.mock.calls[0][0]).toEqual({ template: 'Classify {{current_date}} v3.', commit_message: 'tighten' });
    act(() => {
      saveMutate.mock.calls[0][1].onSuccess({ ...BASE, id: 'router-3', version: 3, labels: [] });
    });
    expect(screen.queryByTestId('save-version')).toBeNull();
    expect(screen.getByTestId('list-pager')).toHaveAttribute('data-current', 'router');
  });

  it('publishes the loaded version from the header gear, and the pager survives the publish', async () => {
    renderDetail();
    // Load v1 (not production) from the Versions grid.
    openTab('Versions');
    fireEvent.click(within(screen.getByTestId('version-row-1')).getByText('seed'));
    openMenu(screen.getByRole('button', { name: 'Actions' }));
    fireEvent.click(await screen.findByRole('menuitem', { name: /Publish v1/ }));
    expect(screen.getByText('Publish router v1 to production?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Publish to production' }));
    expect(labelMutate).toHaveBeenCalledTimes(1);
    expect(labelMutate.mock.calls[0][0]).toEqual({ label: 'production', version_id: 'router-1' });
    act(() => {
      labelMutate.mock.calls[0][1].onSuccess({ labels: { production: 1, staging: null } });
    });
    expect(screen.getByTestId('list-pager')).toHaveAttribute('data-current', 'router');
  });

  it('lists every version in the standard grid, with its labels and date dd/mm/yyyy', () => {
    renderDetail();
    openTab('Versions');
    const v2 = screen.getByTestId('version-row-2');
    expect(v2).toHaveTextContent('v2');
    expect(v2).toHaveTextContent(/production/i);
    expect(v2).toHaveTextContent('Jay');
    expect(v2).toHaveTextContent(/03\/07\/2026/);
    expect(screen.getByTestId('version-row-1')).toHaveTextContent('seed');
  });

  it('loading a version from the grid puts it in the editor on the Prompt tab', () => {
    renderDetail();
    openTab('Versions');
    fireEvent.click(within(screen.getByTestId('version-row-1')).getByText('seed'));
    expect(screen.getByRole('tab', { name: 'Prompt' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText(/\(base: v1\)/)).toBeInTheDocument();
  });

  it('shows the model this prompt runs on in its own tab', () => {
    renderDetail();
    openTab('Model');
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Runs on');
  });
});
