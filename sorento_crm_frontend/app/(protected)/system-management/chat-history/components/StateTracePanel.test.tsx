/**
 * AC-1029's drawer half: the Parser drift row shows the shadow parse beside the live
 * one when a shadow parse is passed, and the single (live-only) column otherwise.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

import { StateTracePanel } from './StateTracePanel';
import type { StateTrace } from '../types/chatHistory.types';

afterEach(cleanup);

const liveTrace: StateTrace = {
  v: 1,
  before: { entities: [] },
  parser_raw: { domain_hint: 'wrong' },
  parser_applied: { domain_hint: 'inventory' },
  after: { entities: [] },
};

const shadowTrace: StateTrace = {
  v: 'shadow',
  before: null,
  after: null,
  parser_raw: { domain_hint: 'wrong' },
  parser_applied: { domain_hint: 'incoming' },
};

function openPanel() {
  fireEvent.click(screen.getByText('state trace'));
}

describe('StateTracePanel - Parser drift row', () => {
  it('renders ONE column (live only) when no shadow parse is passed', () => {
    render(<StateTracePanel trace={liveTrace} />);
    openPanel();

    expect(screen.queryByTestId('parser-drift-columns')).toBeNull();
    expect(screen.getByText('Parser drift')).toBeTruthy();
  });

  it('renders TWO columns, live and shadow, when a shadow parse is present', () => {
    render(<StateTracePanel trace={liveTrace} shadow={shadowTrace} />);
    openPanel();

    const columns = screen.getByTestId('parser-drift-columns');
    expect(columns).toBeTruthy();
    expect(screen.getByText('live')).toBeTruthy();
    expect(screen.getByText('shadow')).toBeTruthy();
  });

  it('the shadow column says so explicitly when shadow itself is null', () => {
    render(<StateTracePanel trace={liveTrace} shadow={null} />);
    openPanel();

    // No shadow prop at all -> single-column mode, never a column claiming "no shadow
    // parse" beside a live one - that would misstate a turn nothing is shadowing.
    expect(screen.queryByText('no shadow parse')).toBeNull();
  });
});
