/**
 * `RuleTesterCard` - S7b Phase 2c gate.
 *
 * Pins two things about the rule tester.
 *
 * Group 1 item 5: it renders three distinct outcomes, HIT, MISS and CANDIDATE
 * (AC-P6b: an unsaved candidate rule can win the ranking; its
 * `deciding_rule.id` is null, so the UI must neither crash on that nor present
 * the winner as if it were saved).
 *
 * Group 2 item 9 (tester half of AC-P24, "strict at write, tolerant at read"):
 * an unknown `match_type` the frontend has no label for renders a readable
 * fallback, never the literal string `undefined`, in BOTH the "deciding rule"
 * summary and the ranked matches list. Both call sites now go through
 * `formatMatchTypeLabel` (see `warrantyLabels.matchTypeLabel.test.ts`) instead
 * of indexing `KIND_RULE_MATCH_TYPE_LABEL` bare, and these tests are what keep
 * either one from regressing back to a bare index.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const testerHook = vi.hoisted(() => ({ useTestKindRules: vi.fn() }));
vi.mock('../hooks/useWarrantyConfig', () => testerHook);

import { RuleTesterCard } from './RuleTesterCard';
import type { KindRuleTestResponse, WarrantyKindRef } from '../types/warranty-config.types';

const KINDS: WarrantyKindRef[] = [{ id: 'kind-mirror', code: 'mirror_cabinet', name: 'Mirror Cabinet' }];

function typeProductCode(value: string) {
  fireEvent.change(screen.getByLabelText('Product code'), { target: { value } });
}

const mutateAsync = vi.fn();

beforeEach(() => {
  mutateAsync.mockReset();
  testerHook.useTestKindRules.mockReturnValue({ mutateAsync, isPending: false });
});

describe('RuleTesterCard - HIT / MISS / CANDIDATE outcomes (AC-P6, AC-P6b, AC-P6c)', () => {
  it('HIT: a saved rule decides the kind, and the deciding rule is named', async () => {
    const response: KindRuleTestResponse = {
      resolved_kind: { id: 'kind-mirror', code: 'mirror_cabinet', name: 'Mirror Cabinet' },
      deciding_rule: {
        id: 'rule-1',
        kind_id: 'kind-mirror',
        match_type: 'model_prefix',
        match_value: 'SRTMCB',
        priority: 0,
        is_candidate: false,
      },
      matches: [
        {
          rank: 1,
          rule: {
            id: 'rule-1',
            kind_id: 'kind-mirror',
            match_type: 'model_prefix',
            match_value: 'SRTMCB',
            priority: 0,
            is_candidate: false,
          },
          kind: { id: 'kind-mirror', code: 'mirror_cabinet', name: 'Mirror Cabinet' },
          matched_length: 6,
          is_candidate: false,
        },
      ],
    };
    mutateAsync.mockResolvedValue(response);

    render(<RuleTesterCard kinds={KINDS} />);
    typeProductCode('SRTMCB6071-BL');
    fireEvent.click(screen.getByRole('button', { name: /^Resolve$/i }));

    // "Mirror Cabinet" appears both as the resolved-kind badge and inside the
    // ranked matches list: assert at least one instance rendered.
    await waitFor(() => expect(screen.getAllByText('Mirror Cabinet').length).toBeGreaterThan(0));
    expect(screen.getByText('Deciding rule')).toBeInTheDocument();
    // "Model prefix" appears both in the deciding-rule summary and the ranked list.
    expect(screen.getAllByText('Model prefix').length).toBeGreaterThan(0);
    expect(screen.getAllByText('SRTMCB').length).toBeGreaterThan(0);
    // A HIT is not decided by an unsaved rule.
    expect(screen.queryByText('Decided by the unsaved rule')).not.toBeInTheDocument();
  });

  it('MISS: no rule reaches any kind, and the copy says so plainly', async () => {
    const response: KindRuleTestResponse = { resolved_kind: null, deciding_rule: null, matches: [] };
    mutateAsync.mockResolvedValue(response);

    render(<RuleTesterCard kinds={KINDS} />);
    typeProductCode('UNKNOWN-CODE');
    fireEvent.click(screen.getByRole('button', { name: /^Resolve$/i }));

    await waitFor(() =>
      expect(screen.getByText('No rule reached a kind for this product.')).toBeInTheDocument(),
    );
    expect(screen.getByText(/Nothing matched\. Add a rule/i)).toBeInTheDocument();
    expect(screen.queryByText('Deciding rule')).not.toBeInTheDocument();
  });

  it('CANDIDATE (AC-P6b): an unsaved candidate rule wins, its id is null, and the UI marks it unsaved without crashing', async () => {
    const response: KindRuleTestResponse = {
      resolved_kind: { id: 'kind-mirror', code: 'mirror_cabinet', name: 'Mirror Cabinet' },
      deciding_rule: {
        id: null,
        kind_id: 'kind-mirror',
        match_type: 'model_prefix',
        match_value: 'SRTMCB6',
        priority: 5,
        is_candidate: true,
      },
      matches: [
        {
          rank: 1,
          rule: {
            id: null,
            kind_id: 'kind-mirror',
            match_type: 'model_prefix',
            match_value: 'SRTMCB6',
            priority: 5,
            is_candidate: true,
          },
          kind: { id: 'kind-mirror', code: 'mirror_cabinet', name: 'Mirror Cabinet' },
          matched_length: 7,
          is_candidate: true,
        },
      ],
    };
    mutateAsync.mockResolvedValue(response);

    render(<RuleTesterCard kinds={KINDS} />);
    typeProductCode('SRTMCB6071-BL');
    fireEvent.click(screen.getByRole('button', { name: /^Resolve$/i }));

    // No crash on a null `deciding_rule.id`: the winner still renders.
    // "Mirror Cabinet" appears both as the resolved-kind badge and inside the
    // ranked matches list: assert at least one instance rendered.
    await waitFor(() => expect(screen.getAllByText('Mirror Cabinet').length).toBeGreaterThan(0));
    expect(screen.getByText('Decided by the unsaved rule')).toBeInTheDocument();
    expect(screen.getByText('Unsaved')).toBeInTheDocument();
  });
});

describe('RuleTesterCard - AC-P24 tolerant read: an unrecognised match_type never renders literal "undefined"', () => {
  it('renders a readable fallback for the deciding rule and the ranked match, not undefined', async () => {
    const response: KindRuleTestResponse = {
      resolved_kind: { id: 'kind-mirror', code: 'mirror_cabinet', name: 'Mirror Cabinet' },
      deciding_rule: {
        id: 'rule-9',
        kind_id: 'kind-mirror',
        // @ts-expect-error - deliberately a match_type the FE label map does not know.
        match_type: 'something_new',
        match_value: 'ABC',
        priority: 0,
        is_candidate: false,
      },
      matches: [
        {
          rank: 1,
          rule: {
            id: 'rule-9',
            kind_id: 'kind-mirror',
            // @ts-expect-error - same unknown value in the ranked list.
            match_type: 'something_new',
            match_value: 'ABC',
            priority: 0,
            is_candidate: false,
          },
          kind: { id: 'kind-mirror', code: 'mirror_cabinet', name: 'Mirror Cabinet' },
          matched_length: 3,
          is_candidate: false,
        },
      ],
    };
    mutateAsync.mockResolvedValue(response);

    render(<RuleTesterCard kinds={KINDS} />);
    typeProductCode('ABC-1');
    fireEvent.click(screen.getByRole('button', { name: /^Resolve$/i }));

    // "Mirror Cabinet" appears both as the resolved-kind badge and inside the
    // ranked matches list: assert at least one instance rendered.
    await waitFor(() => expect(screen.getAllByText('Mirror Cabinet').length).toBeGreaterThan(0));

    // JSX silently renders `undefined` as NOTHING, not the literal string
    // "undefined", so a naive `queryByText('undefined')` check would pass even
    // though `KIND_RULE_MATCH_TYPE_LABEL['something_new']` is blank. The real
    // requirement is a READABLE fallback (e.g. the raw match_type), not silence.
    const decidingRuleRow = screen.getByText('Deciding rule').closest('div');
    expect(decidingRuleRow?.textContent ?? '').toContain('something_new');

    const matchListItems = screen.getAllByRole('listitem');
    expect(matchListItems).toHaveLength(1);
    expect(matchListItems[0].textContent ?? '').toContain('something_new');
  });
});
