/**
 * CHAT-INDEX-VIZ FE-1: the per-turn "Index match" section (contract:
 * documentation/plans/chatbot/chat-index-viz-20oct-contract.md). Written before the component exists.
 * Synthetic ZZ data only.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';

import { IndexMatchSection } from './IndexMatchSection';
import type { IndexMatch } from '../types/chatbotTurn.types';

afterEach(() => cleanup());

const WAREHOUSE_DROPPED = 'Dropped: a finish code ending, not on the warehouse list';

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
        matched: [
          { list: 'Specifications', entry: 'spec finish = french_gold (French Gold)', close_spelling: false },
        ],
        parser_got: ['- "frg": spec finish = french_gold (French Gold)'],
        understood: [{ text: '"frg" as a specification: finish = french_gold' }, { text: '"frg" as a warehouse' }],
        result: [
          { outcome: 'kept', text: 'Kept' },
          { outcome: 'dropped', text: WAREHOUSE_DROPPED },
        ],
      },
      {
        word: 'whyte',
        matched: [{ list: 'Specifications', entry: 'spec finish = white (White)', close_spelling: true }],
        parser_got: ['- "whyte": near spec finish = white (White)'],
        understood: [{ text: '"whyte" as a specification: finish = white' }],
        result: [{ outcome: 'changed', text: 'Changed: read as Finish = white' }],
      },
    ],
    held: ['spec finish = chrome (Chrome)', 'File type zz_idx_drawing: ZZ Idx Drawing.'],
    not_from_lists: [{ text: '"IB" as a warehouse', outcome: 'kept', result: 'Kept' }],
    failed: false,
    ...over,
  };
}

describe('IndexMatchSection', () => {
  it('shows the empty text when the turn sent the full lists (null)', () => {
    render(<IndexMatchSection indexMatch={null} />);
    expect(screen.getByText('No list matching was recorded on this turn.')).toBeInTheDocument();
  });

  it('shows one line when the matching step failed', () => {
    render(<IndexMatchSection indexMatch={fixture({ failed: true, rows: [], held: [], not_from_lists: [] })} />);
    expect(
      screen.getByText('The matching step failed on this turn; the parser ran without it.'),
    ).toBeInTheDocument();
  });

  it('renders the message words as chips, matched or not', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    expect(screen.getAllByText('zzstock').length).toBeGreaterThan(0);
    expect(screen.getAllByText('frg').length).toBeGreaterThan(0);
    expect(screen.getAllByText('whyte').length).toBeGreaterThan(0);
  });

  it('has the five flow labels, exactly', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    for (const label of ['Word', 'Matched list entry', 'What the parser got', 'What it understood', 'Kept or dropped']) {
      expect(screen.getAllByText(label).length, label).toBeGreaterThan(0);
    }
  });

  it('renders one row per word, in order, with entry, parser lines, understood and outcome', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    const frg = screen.getByTestId('index-row-frg');
    expect(frg).toHaveTextContent('spec finish = french_gold (French Gold)');
    expect(frg).toHaveTextContent('- "frg": spec finish = french_gold (French Gold)');
    expect(frg).toHaveTextContent('"frg" as a specification: finish = french_gold');
    expect(frg).toHaveTextContent('"frg" as a warehouse');
    expect(screen.getByTestId('index-row-whyte')).toBeInTheDocument();
    const rows = screen.getAllByTestId(/^index-row-/);
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual(['index-row-frg', 'index-row-whyte']);
  });

  it('shows kept, dropped and changed outcomes as badges with the written words', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    const frg = screen.getByTestId('index-row-frg');
    expect(within(frg).getByText('Kept')).toBeInTheDocument();
    expect(within(frg).getByText('Dropped')).toBeInTheDocument();
    expect(frg).toHaveTextContent(WAREHOUSE_DROPPED);
    expect(screen.getByTestId('index-row-whyte')).toHaveTextContent('Changed: read as Finish = white');
  });

  it('marks a close spelling next to the entry, and only there', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    expect(screen.getByTestId('index-row-whyte')).toHaveTextContent('close spelling');
    expect(screen.getByTestId('index-row-frg')).not.toHaveTextContent('close spelling');
  });

  it('lists entities that matched no row after the rows, under "(not from the lists)"', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    expect(screen.getByText('(not from the lists)')).toBeInTheDocument();
    expect(screen.getByText('"IB" as a warehouse')).toBeInTheDocument();
  });

  it('keeps each understood item on the same line as its result, the badge holding only the outcome word', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    const frg = screen.getByTestId('index-row-frg');
    const outcomes = within(frg).getAllByTestId('index-outcome');
    expect(outcomes).toHaveLength(2);
    expect(outcomes[0].parentElement?.parentElement).toHaveTextContent('"frg" as a specification: finish = french_gold');
    expect(outcomes[1].parentElement?.parentElement).toHaveTextContent('"frg" as a warehouse');
    expect(within(frg).getByText('Dropped').textContent).toBe('Dropped');
  });

  it('shows a muted dash under understood and kept or dropped when the parser did not use the word', () => {
    const unused = {
      word: 'zzidle',
      matched: [{ list: 'File types', entry: 'File type zz_photos: ZZ Photos.', close_spelling: false }],
      parser_got: ['File type zz_photos: ZZ Photos.'],
      understood: [],
      result: [],
    };
    render(<IndexMatchSection indexMatch={fixture({ rows: [unused] })} />);
    const row = screen.getByTestId('index-row-zzidle');
    expect(within(row).getAllByText('-')).toHaveLength(2);
  });

  it('shows one line instead of an empty grid when no word matched', () => {
    render(<IndexMatchSection indexMatch={fixture({ rows: [], not_from_lists: [], held: [] })} />);
    expect(screen.getByText('No word of this message matched a list entry.')).toBeInTheDocument();
    expect(screen.queryByText('Matched list entry')).toBeNull();
  });

  it('keeps the held lines in a closed collapsible that opens on click', () => {
    render(<IndexMatchSection indexMatch={fixture()} />);
    const trigger = screen.getByText('Also sent: 2 lines on record for the held product');
    expect(screen.queryByText('spec finish = chrome (Chrome)')).toBeNull();
    fireEvent.click(trigger);
    expect(screen.getByText('spec finish = chrome (Chrome)')).toBeInTheDocument();
  });

  it('has no held collapsible when nothing is held', () => {
    render(<IndexMatchSection indexMatch={fixture({ held: [] })} />);
    expect(screen.queryByText(/Also sent:/)).toBeNull();
  });

  it('prints no internal names', () => {
    const { container } = render(<IndexMatchSection indexMatch={fixture()} />);
    const text = (container.textContent ?? '').toLowerCase();
    for (const internal of ['grounding', 'hidden_keys', 'index mode', 'closed_lists_index', 'system_blanks']) {
      expect(text).not.toContain(internal);
    }
  });
});
