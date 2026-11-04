/**
 * CONFIRM-DIALOG-SPEED (crew measure of #2128, 3 Nov 2026): while the guided Confirm reads a
 * page's purchasing-email words (`RemarkWordsPendingContext`), no REMARK cell may print words
 * that are not the planner's own draft remark: not the sheet's generated change words on a
 * delivered line, not a carried line's old confirmed remark. Each reads
 * "Preparing email preview..." until the email's words land.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  LineSplitSheet,
  RemarkWordsPendingContext,
  type SheetHandlers,
} from './LineSplitSheet';
import { fromPayload, sortLines, type SplitLine } from '../lib/lineSplitModel';
import { ownerSavedCase } from '@/test-mocks/lineSplitSheetKit';

function handlers(): SheetHandlers {
  return {
    open: vi.fn(), qty: vi.fn(), date: vi.fn(), remark: vi.fn(),
    add: vi.fn(), remove: vi.fn(), fieldBlur: vi.fn(), lineRemark: vi.fn(),
  };
}

function renderSheet(patch: (line: SplitLine) => SplitLine, lineNo: number, pending: boolean) {
  const all = sortLines(fromPayload(ownerSavedCase() as never)).map((line) =>
    line.lineNo === lineNo ? patch(line) : line,
  );
  const lines = all.filter((line) => line.lineNo === lineNo);
  render(
    <RemarkWordsPendingContext.Provider value={pending}>
      <LineSplitSheet
        readOnly={false}
        lines={lines}
        allLines={all}
        savedLines={all}
        soNumber="SO417636"
        soDate="2026-09-03"
        openLineIds={new Set()}
        drag={null}
        overTarget={null}
        flashLineId={null}
        handlers={handlers()}
      />
    </RemarkWordsPendingContext.Provider>,
  );
  return screen.getByTestId(`split-line-${lineNo}`);
}

const delivered = (line: SplitLine): SplitLine => ({
  ...line,
  deliveredInFull: true,
  deliveredQty: line.baseQty,
  pendingChange: true,
  remarkGenerated: 'GENERATED WORDS',
  savedRemark: null,
  ownRemark: '',
});

const carried = (line: SplitLine): SplitLine => ({
  ...line,
  savedRemark: null,
  ownRemark: 'OLD CONFIRMED',
  remarkInDraft: false,
});

describe('REMARK cells while the email words are pending', () => {
  it('(1) a delivered line with no remark prints "Preparing email preview...", not the generated words', () => {
    const block = renderSheet(delivered, 608, true);
    expect(block).not.toHaveTextContent('GENERATED WORDS');
    expect(within(block).getByTestId('remark-words-pending')).toHaveTextContent(
      'Preparing email preview...',
    );
  });

  it('(1) once the words are in, the delivered line prints its generated words as before', () => {
    const block = renderSheet(delivered, 608, false);
    expect(block).toHaveTextContent('GENERATED WORDS');
  });

  it('(2) a carried line with no decision prints "Preparing email preview...", not its old confirmed remark', () => {
    const block = renderSheet(carried, 768, true);
    expect(block).not.toHaveTextContent('OLD CONFIRMED');
    expect(within(block).getByTestId('remark-words-pending')).toHaveTextContent(
      'Preparing email preview...',
    );
  });

  it('(2) once the words are in, the carried line shows its confirmed remark as before', () => {
    renderSheet(carried, 768, false);
    expect((screen.getByLabelText('Remark, line 768') as HTMLTextAreaElement).value).toBe(
      'OLD CONFIRMED',
    );
  });

  it('a draft line\'s own remark is the planner\'s and still shows while pending', () => {
    const block = renderSheet(
      (line) => ({ ...line, savedRemark: null, ownRemark: 'MY REMARK', remarkInDraft: true }),
      768,
      true,
    );
    expect(block).toHaveTextContent('MY REMARK');
  });
});
