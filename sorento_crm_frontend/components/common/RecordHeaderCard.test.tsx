import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RecordHeaderCard } from './RecordHeaderCard';

describe('RecordHeaderCard (the Order Inquiry record card, shared)', () => {
  it('puts the number and the badges in one title row, each subtitle on its own line, actions beside', () => {
    render(
      <RecordHeaderCard
        title="OI-2609-0002"
        badges={<span>Outstanding</span>}
        subtitle={[
          'Raised by Ahmad on 05/11/2026, 2:14 pm',
          <span key="x">Second line</span>,
        ]}
        actions={<button type="button">Confirm</button>}
      />,
    );
    const card = screen.getByTestId('record-header-card');
    const row = within(card).getByTestId('record-header-title-row');
    expect(
      within(row).getByRole('heading', { name: 'OI-2609-0002' }),
    ).toBeInTheDocument();
    expect(within(row).getByText('Outstanding')).toBeInTheDocument();
    const lines = within(card).getAllByTestId('record-header-subtitle');
    expect(lines.map((el) => el.textContent)).toEqual([
      'Raised by Ahmad on 05/11/2026, 2:14 pm',
      'Second line',
    ]);
    expect(
      within(card).getByRole('button', { name: 'Confirm' }),
    ).toBeInTheDocument();
  });

  it('drops empty subtitle entries and renders children under the row', () => {
    render(
      <RecordHeaderCard title="X" subtitle={[null, false, 'Only']}>
        <p>Countdown</p>
      </RecordHeaderCard>,
    );
    expect(screen.getAllByTestId('record-header-subtitle')).toHaveLength(1);
    expect(screen.getByText('Countdown')).toBeInTheDocument();
  });
});
