/**
 * The thin bar under a quantity that says where it is coming from (AC-C1, AC-C3).
 *
 * The captain, on the grid: "a cell says nothing about the suggestion until it is opened". So
 * the proportions are load-bearing - a cell that is mostly Buy has to LOOK mostly Buy from
 * across the board - and so is the opacity, which is the difference between what the engine
 * suggests and what somebody has committed to.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SupplyBar } from './SupplyBar';
import { COLOURS } from '../../_shared/lib/supplyVocabulary';

function segments() {
  return screen.getByTestId('supply-bar').querySelectorAll('span[data-kind]');
}

describe('SupplyBar', () => {
  it('draws one solid segment when a cell has one kind (AC-C1)', () => {
    render(<SupplyBar segments={[{ kind: 'buy', qty: '71' }]} decided />);

    const drawn = segments();
    expect(drawn).toHaveLength(1);
    expect(drawn[0].getAttribute('data-kind')).toBe('buy');
    expect((drawn[0] as HTMLElement).style.width).toBe('100%');
    expect(drawn[0].className).toContain(COLOURS.buy.bar);
  });

  it('splits a mixed cell in proportion to the quantities (AC-C1)', () => {
    render(
      <SupplyBar
        segments={[
          { kind: 'buy', qty: '25' },
          { kind: 'shared', qty: '75' },
        ]}
        decided
      />,
    );

    const drawn = segments();
    expect(drawn).toHaveLength(2);
    expect((drawn[0] as HTMLElement).style.width).toBe('25%');
    expect((drawn[1] as HTMLElement).style.width).toBe('75%');
    expect(drawn[1].className).toContain(COLOURS.shared.bar);
  });

  it('names each segment in words, because a colour alone is not a label', () => {
    render(<SupplyBar segments={[{ kind: 'own', qty: '454' }]} decided />);

    expect(segments()[0].getAttribute('title')).toBe('Use own location 454');
  });

  it('draws a decided bar solid and a suggested one faded (AC-C3)', () => {
    const { rerender } = render(
      <SupplyBar segments={[{ kind: 'shared', qty: '71' }]} decided />,
    );
    expect(screen.getByTestId('supply-bar').className).toContain('opacity-100');

    rerender(<SupplyBar segments={[{ kind: 'shared', qty: '71' }]} decided={false} />);
    expect(screen.getByTestId('supply-bar').className).toContain('opacity-50');
  });

  it('draws nothing at all when there is nothing to draw', () => {
    const { rerender } = render(<SupplyBar segments={[]} decided={false} />);
    expect(screen.queryByTestId('supply-bar')).not.toBeInTheDocument();

    // A composition that is entirely zero is not a bar of zero-width segments: it is no bar.
    rerender(<SupplyBar segments={[{ kind: 'buy', qty: '0' }]} decided={false} />);
    expect(screen.queryByTestId('supply-bar')).not.toBeInTheDocument();
  });
});
