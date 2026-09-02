/**
 * M3-02 (`ui-motion-round2`) - the funded-vs-budget fill bar animates
 * `transform`, not `width` (GPU properties guardrail).
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CashBudgetPanel } from './CashBudgetPanel';
import type { FundingResult } from '../lib/reorderCashAllocation';

function funding(overrides: Partial<FundingResult> = {}): FundingResult {
  return {
    funded: [],
    deferred: [],
    needsCost: [],
    fundedCash: 500,
    deferredCash: 0,
    remaining: 500,
    ...overrides,
  };
}

function bar() {
  return screen.getByRole('progressbar').querySelector('div') as HTMLElement;
}

describe('CashBudgetPanel fill bar', () => {
  it('animates scaleX from origin-left on the tokens, never width', () => {
    render(
      <CashBudgetPanel
        budget={1000}
        onBudgetChange={vi.fn()}
        sliderMax={5000}
        step={100}
        funding={funding({ fundedCash: 500 })}
      />,
    );
    const fill = bar();
    expect(fill.className).toContain('origin-left');
    expect(fill.className).toContain('transition-transform');
    expect(fill.className).toContain('duration-(--duration-base)');
    expect(fill.className).toContain('motion-reduce:transition-none');
    expect(fill.style.transform).toBe('scaleX(0.5)');
    expect(fill.style.width).toBe('');
  });

  it('caps the fill at scaleX(1) when funded cash meets or exceeds the budget', () => {
    render(
      <CashBudgetPanel
        budget={1000}
        onBudgetChange={vi.fn()}
        sliderMax={5000}
        step={100}
        funding={funding({ fundedCash: 1500 })}
      />,
    );
    expect(bar().style.transform).toBe('scaleX(1)');
  });

  it('renders no fill when budget is zero', () => {
    render(
      <CashBudgetPanel
        budget={0}
        onBudgetChange={vi.fn()}
        sliderMax={5000}
        step={100}
        funding={funding({ fundedCash: 0 })}
      />,
    );
    expect(bar().style.transform).toBe('scaleX(0)');
  });
});
