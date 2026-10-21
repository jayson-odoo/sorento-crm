/**
 * CHAT-INDEX-VIZ FE-1 (contract v2 amendment): the per-turn "Index match" section.
 * Synthetic ZZ data only.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';

import { IndexMatchSection } from './IndexMatchSection';
import type { IndexMatch } from '../types/chatbotTurn.types';

afterEach(() => cleanup());

const WAREHOUSE_DROPPED = 'Dropped: a finish code ending, not on the warehouse list';
const RAW_LINE = '- "frg": spec finish = french_gold (French Gold)';

function fixture(over: Partial<IndexMatch> = {}): IndexMatch {
  return {
    words: [
      { text: 'zzstock', matched: false },
      { text: 'frg', matched: true },
      { text: 'whyte', matched: true },
    ],
    rows: [
      {
        word: 'frg',
        matched: [{ plain: 'Finish: French Gold', source: 'from the product finish list (code ending -FRG)', close_spelling: false }],
        parser_got: [RAW_LINE],
        understood: [{ text: '"frg" read as Finish: French Gold' }, { text: '"frg" read as a warehouse' }],
        result: [
          { outcome: 'kept', text: 'Kept' },
          { outcome: 'dropped', text: WAREHOUSE_DROPPED },
        ],
      },
      {
        word: 'whyte',
        matched: [{ plain: 'Finish: White', source: 'from the product finish list', close_spelling: true }],
        parser_got: ['- "whyte": near spec finish = white (White)'],
        understood: [{ text: '"whyte" read as Finish: White' }],
        result: [{ outcome: 'changed', text: 'Changed: read as Finish: White' }],
      },
    ],
    held: ['Finish: Chrome', 'ZZ Idx Drawing'],
    not_from_lists: [{ text: '"IB" read as a warehouse', outcome: 'kept', result: 'Kept' }],
    failed: false,
    looked_up: { what: 'Check stock levels', details: ['Product code: ZZP1', 'Warehouse codes: ZZA, ZZB'] },
    ...over,
  };
}

describe('IndexMatchSection', () => {
  it('shows the empty text when no matching was recorded (null)', () => {
    render(<IndexMatchSection indexMatch={null} />);
    expect(screen.getByText('No list matching was recorded on this turn.')).toBeInTheDocument();
  });

  it('shows one line when the matching step failed', () => {
    render(<IndexMatchSection indexMatch={fixture({ failed: true, rows: [], held: [], not_from_lists: [] })} />);
    expect(screen.getByText('The matching step failed on this turn; the bot ran without it.')).toBeInTheDocument();
  });

  it('renders the message words as chips, matched or not', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    expect(screen.getAllByText('zzstock').length).toBeGreaterThan(0);
    expect(screen.getAllByText('frg').length).toBeGreaterThan(0);
  });

  it('has exactly the four visible column labels', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    for (const label of ['Word', 'Matched list entry', 'What the bot understood', 'Kept or dropped']) {
      expect(screen.getAllByText(label).length, label).toBeGreaterThan(0);
    }
    expect(screen.queryByText('What the parser got')).toBeNull();
    expect(screen.queryByText('What it understood')).toBeNull();
  });

  it('shows the plain value and, muted, the source of each matched entry', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    const frg = screen.getByTestId('index-row-frg');
    expect(frg).toHaveTextContent('Finish: French Gold');
    expect(frg).toHaveTextContent('from the product finish list (code ending -FRG)');
    expect(frg).toHaveTextContent('"frg" read as a warehouse');
    const rows = screen.getAllByTestId(/^index-row-/);
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual(['index-row-frg', 'index-row-whyte']);
  });

  it('keeps the raw lines out of sight until Show details is pressed', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    expect(screen.queryByText(RAW_LINE)).toBeNull();
    expect(screen.queryByText('What the bot was given')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show details' }));
    const frg = screen.getByTestId('index-row-frg');
    expect(within(frg).getByText('What the bot was given')).toBeInTheDocument();
    expect(within(frg).getByText(RAW_LINE)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Hide details' }));
    expect(screen.queryByText(RAW_LINE)).toBeNull();
  });

  it('shows kept, dropped and changed outcomes as badges with the written words', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    const frg = screen.getByTestId('index-row-frg');
    expect(within(frg).getByText('Kept')).toBeInTheDocument();
    expect(within(frg).getByText('Dropped')).toBeInTheDocument();
    expect(frg).toHaveTextContent(WAREHOUSE_DROPPED);
    expect(screen.getByTestId('index-row-whyte')).toHaveTextContent('Changed: read as Finish: White');
  });

  it('marks a close spelling next to the entry, and only there', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    expect(screen.getByTestId('index-row-whyte')).toHaveTextContent('close spelling');
    expect(screen.getByTestId('index-row-frg')).not.toHaveTextContent('close spelling');
  });

  it('lists entities that matched no row after the rows, under "(not from the lists)"', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    expect(screen.getByText('(not from the lists)')).toBeInTheDocument();
    expect(screen.getByText('"IB" read as a warehouse')).toBeInTheDocument();
  });

  it('keeps each understood item on the same line as its result', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    const outcomes = within(screen.getByTestId('index-row-frg')).getAllByTestId('index-outcome');
    expect(outcomes).toHaveLength(2);
    expect(outcomes[0].parentElement?.parentElement).toHaveTextContent('"frg" read as Finish: French Gold');
    expect(outcomes[1].parentElement?.parentElement).toHaveTextContent('"frg" read as a warehouse');
  });

  it('shows a muted dash when the bot did not use the word', () => {
    const unused = {
      word: 'zzidle',
      matched: [{ plain: 'ZZ Photos', source: 'from the file type list', close_spelling: false }],
      parser_got: ['File type zz_photos: ZZ Photos.'],
      understood: [],
      result: [],
    };
    render(<IndexMatchSection indexMatch={fixture({ rows: [unused] })} />);
    expect(within(screen.getByTestId('index-row-zzidle')).getAllByText('-')).toHaveLength(2);
  });

  it('shows one line instead of an empty grid when no word matched', () => {
    render(<IndexMatchSection indexMatch={fixture({ rows: [], not_from_lists: [], held: [] })} />);
    expect(screen.getByText('No word of this message matched a list entry.')).toBeInTheDocument();
    expect(screen.queryByText('Matched list entry')).toBeNull();
  });

  it('shows what the bot looked up, with its details, and nothing when it looked up nothing', () => {
    const { unmount } = render(<IndexMatchSection indexMatch={fixture()} />);
    const block = screen.getByTestId('index-looked-up');
    expect(within(block).getByText('What the bot looked up')).toBeInTheDocument();
    expect(block).toHaveTextContent('Check stock levels');
    expect(block).toHaveTextContent('Product code: ZZP1');
    expect(block).toHaveTextContent('Warehouse codes: ZZA, ZZB');
    unmount();
    render(<IndexMatchSection indexMatch={fixture({ looked_up: null })} />);
    expect(screen.queryByText('What the bot looked up')).toBeNull();
  });

  it('keeps the held lines in a closed collapsible that opens on click', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    const trigger = screen.getByText('Also sent: 2 lines on record for the held product');
    expect(screen.queryByText('Finish: Chrome')).toBeNull();
    fireEvent.click(trigger);
    expect(screen.getByText('Finish: Chrome')).toBeInTheDocument();
  });

  it('has no held collapsible when nothing is held', () => {
    render(<IndexMatchSection indexMatch={fixture({ held: [] })} />);
    expect(screen.queryByText(/Also sent:/)).toBeNull();
  });

  it('prints no internal words or snake_case on screen, even with the details open', () => {
    const { container } = render(<IndexMatchSection indexMatch={fixture()} />);
    const visible = (container.textContent ?? '').toLowerCase();
    for (const internal of ['parser', 'token', 'grounding', 'hidden_keys', 'index mode', 'closed_lists_index', 'system_blanks']) {
      expect(visible, internal).not.toContain(internal);
    }
    expect(visible).not.toMatch(/[a-z]_[a-z]/);
  });
});
