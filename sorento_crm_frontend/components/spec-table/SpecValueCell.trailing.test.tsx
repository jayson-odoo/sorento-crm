/**
 * SPEC-ICON-COMBINED FU F2: with trailing icons the value keeps its own width: the button is
 * `shrink-0` (never `min-w-0`) and the trailing block wraps below it instead of squeezing it.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SpecValueCell } from './SpecValueCell';
import type { SpecTableRow } from './types';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const ROW = {
  specKey: 'trap_length', label: 'Trap length', value: 150, unit: 'mm', dataType: 'numeric',
  options: [], source: 'derived', evidence: null, unknownKey: false, valueLabels: {}, conflict: null,
} as unknown as SpecTableRow;

describe('FU F2 SpecValueCell with trailing', () => {
  it('the value button cannot shrink below its content and the row wraps', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <SpecValueCell
          row={ROW}
          editing={false}
          draft=""
          onDraftChange={() => {}}
          onStartEdit={() => {}}
          onCancel={() => {}}
          onSave={async () => {}}
          trailing={<span data-testid="trail">icons</span>}
        />
      </QueryClientProvider>,
    );
    const button = screen.getByRole('button', { name: /150/ });
    expect(button.className).toContain('shrink-0');
    expect(button.className).not.toContain('min-w-0');
    expect(button.parentElement?.className).toContain('flex-wrap');
  });
});
