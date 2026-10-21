/**
 * CHAT-INDEX-VIZ FE-2: the prompt "Architecture" tab body (contract:
 * documentation/plans/chatbot/chat-index-viz-20oct-contract.md). Written before the component exists.
 * Assumed props: `{ name: string; version: number }`; the component reads `usePromptArchitecture`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { PromptArchitecture } from './PromptArchitecture';
import type { PromptArchitecture as Architecture } from '../../services/aiPromptsService';

const usePromptArchitecture = vi.fn();
vi.mock('../../hooks/useAIAssistantPrompts', () => ({
  usePromptArchitecture: (...args: unknown[]) => usePromptArchitecture(...args),
}));

const DATA: Architecture = {
  version: 77,
  mode: 'index',
  uses_closed_lists: true,
  total_size: 35700,
  groups: [
    { name: 'Rules', size: 28000, share: 0.784 },
    { name: 'Examples', size: 6000, share: 0.168 },
    { name: 'Product lists', size: 891, share: 0.025 },
    { name: 'Lists from other settings', size: 809, share: 0.023 },
  ],
  lists: [
    { key: 'specs', name: 'Specifications', source: 'Product Specifications', href: '/master-data-management/product-specifications', how: 'HOW-SPECS sentence.', entries: 42, sent_each_message_size: 36, full_list_size: 5120 },
    { key: 'attachment_types', name: 'File types', source: 'Attachment Types', href: '/resource-management/attachment-types', how: 'HOW-FILES sentence.', entries: 7, sent_each_message_size: 22, full_list_size: 480 },
    { key: 'certification_types', name: 'Certificates', source: 'Certificates', href: '/master-data-management/certificates', how: 'HOW-CERTS sentence.', entries: 5, sent_each_message_size: 25, full_list_size: 300 },
    { key: 'warehouses', name: 'Warehouses', source: 'Warehouses', href: '/inventory-management/warehouses', how: 'HOW-WH sentence.', entries: 9, sent_each_message_size: 0, full_list_size: 0, checked_only: true },
  ],
};

function rowOf(text: string): HTMLElement {
  const row = screen.getAllByText(text).map((el) => el.closest('tr')).find(Boolean);
  expect(row, `a table row holding "${text}"`).toBeTruthy();
  return row as HTMLElement;
}

beforeEach(() => {
  usePromptArchitecture.mockReset().mockReturnValue({ data: DATA, isLoading: false, isError: false });
});
afterEach(() => cleanup());

describe('PromptArchitecture', () => {
  it('asks for the architecture of the given key and version', () => {
    render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    expect(usePromptArchitecture).toHaveBeenCalled();
    const args = usePromptArchitecture.mock.calls[0];
    expect(args[0]).toBe('chatbot_semantic_parser');
    expect(args[1]).toBe(77);
  });

  it('has the root test id', () => {
    render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    expect(screen.getByTestId('prompt-architecture')).toBeInTheDocument();
  });

  it('shows the summary line and the index badge', () => {
    render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    expect(
      screen.getByText('Each message, v77 gives the bot about 35.7k of instructions and lists.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Only the matching entries are sent')).toBeInTheDocument();
    expect(screen.queryByText('Full lists are sent')).toBeNull();
  });

  it('shows the full-lists badge in block mode', () => {
    usePromptArchitecture.mockReturnValue({ data: { ...DATA, mode: 'block' }, isLoading: false, isError: false });
    render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    expect(screen.getByText('Full lists are sent')).toBeInTheDocument();
    expect(screen.queryByText('Only the matching entries are sent')).toBeNull();
  });

  it('shows the full-lists badge in index mode when the version has no closed lists section', () => {
    usePromptArchitecture.mockReturnValue({
      data: { ...DATA, uses_closed_lists: false },
      isLoading: false,
      isError: false,
    });
    render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    expect(screen.getByText('Full lists are sent')).toBeInTheDocument();
  });

  it('draws the five flow boxes with the written labels', () => {
    render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    for (const label of [
      "Customer's message",
      'Matched list entries',
      'What the bot was given',
      'What the bot understood',
      'Kept or dropped',
      'What the bot looked up',
    ]) {
      expect(screen.getByText(label), label).toBeInTheDocument();
    }
    expect(screen.getByText('Checked against the same lists and the warehouse list')).toBeInTheDocument();
  });

  it('names the lists under "Matched list entries", leaving the checked-only warehouses out', () => {
    render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    expect(screen.getAllByText('Specifications').some((el) => !el.closest('tr'))).toBe(true);
    expect(screen.getAllByText('File types').some((el) => !el.closest('tr'))).toBe(true);
    expect(screen.getAllByText('Warehouses').every((el) => el.closest('tr'))).toBe(true);
  });

  it('has the Lists table with its columns and one row per list', () => {
    render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    for (const col of ['List', 'Comes from', 'How a message is matched', 'Entries', 'Size each message', 'Full list size']) {
      expect(screen.getAllByText(col).length, col).toBeGreaterThan(0);
    }
    const specs = rowOf('Specifications');
    expect(specs).toHaveTextContent('42');
    expect(specs).toHaveTextContent('36');
    expect(specs).toHaveTextContent('5.1k');
    expect(specs).toHaveTextContent('HOW-SPECS sentence.');
    const link = within(specs).getByRole('link', { name: 'Product Specifications' });
    expect(link.getAttribute('href')).toBe('/master-data-management/product-specifications');
  });

  it('shows "-" for both sizes of a checked-only list', () => {
    render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    const warehouses = rowOf('Warehouses');
    expect(warehouses).toHaveTextContent('9');
    expect(within(warehouses).getAllByText('-')).toHaveLength(2);
    expect(within(rowOf('Specifications')).queryByText('-')).toBeNull();
  });

  it('has the "What the bot is given" table with the groups only, sizes formatted, no heading names', () => {
    render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    expect(screen.getAllByText('What the bot is given').length).toBeGreaterThan(0);
    for (const col of ['Part', 'Size']) {
      expect(screen.getAllByText(col).length, col).toBeGreaterThan(0);
    }
    expect(rowOf('Rules')).toHaveTextContent('28.0k');
    expect(rowOf('Examples')).toHaveTextContent('6.0k');
    expect(rowOf('Product lists')).toHaveTextContent('891');
    expect(rowOf('Product lists')).not.toHaveTextContent('0.9k');
    expect(rowOf('Lists from other settings')).toHaveTextContent('809');
    expect(screen.queryByText('Sections')).toBeNull();
  });

  it('labels every table cell so each row can stack as "label: value" on a phone', () => {
    const { container } = render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    const cells = Array.from(container.querySelectorAll('tbody td'));
    expect(cells.length).toBeGreaterThan(0);
    for (const cell of cells) expect(cell.getAttribute('data-label'), cell.textContent ?? '').toBeTruthy();
    // On a phone the rows stack, so nothing scrolls sideways there; between sm
    // and a wide screen each table still sits in its own scroller (S4-04).
    const tables = Array.from(container.querySelectorAll('table'));
    expect(tables).toHaveLength(2);
    for (const table of tables) {
      expect(table).toHaveClass('max-sm:block');
      expect(table.parentElement).toHaveClass('overflow-x-auto');
    }
  });

  it('lays the six flow boxes out three to a row from sm and six to a row only from 2xl', () => {
    render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    const flow = screen.getByTestId('architecture-flow');
    expect(flow.className).toContain('sm:grid-cols-3');
    expect(flow.className).toContain('2xl:grid-cols-6');
  });

  it('shows one error line when the architecture cannot be loaded', () => {
    usePromptArchitecture.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    expect(screen.getByText('Could not load the architecture for this version.')).toBeInTheDocument();
    expect(screen.queryByText(/gives the bot about/)).toBeNull();
  });

  it('shows neither the summary nor the error while loading', () => {
    usePromptArchitecture.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    expect(screen.queryByText(/gives the bot about/)).toBeNull();
    expect(screen.queryByText('Could not load the architecture for this version.')).toBeNull();
  });

  it('prints no internal names', () => {
    const { container } = render(<PromptArchitecture name="chatbot_semantic_parser" version={77} />);
    const text = (container.textContent ?? '').toLowerCase();
    for (const internal of ['parser', 'token', 'grounding', 'hidden_keys', 'closed_lists_index', 'system_blanks', 'index mode']) {
      expect(text, internal).not.toContain(internal);
    }
    expect(text).not.toMatch(/[a-z]_[a-z]/);
  });
});
