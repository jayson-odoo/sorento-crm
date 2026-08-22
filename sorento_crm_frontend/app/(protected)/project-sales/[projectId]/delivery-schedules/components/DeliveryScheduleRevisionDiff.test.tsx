/**
 * P6 section 9.1 - was -> now on a schedule revision.
 *
 * Dates come off the version's own `promoted_delivery_date`; quantities need the full prior
 * version, which the review screen fetches separately and this component only renders once
 * handed. Both cases, and the "still comparing" / "nothing moved" fallbacks, are pinned here.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { DeliveryScheduleVersion } from '../../../_shared/types/deliverySchedule.types';
import { DeliveryScheduleRevisionDiff } from './DeliveryScheduleRevisionDiff';

function version(overrides: Partial<DeliveryScheduleVersion> = {}): DeliveryScheduleVersion {
  return {
    id: 'v2',
    delivery_schedule_id: 's1',
    version_no: 2,
    revision_label: 'REVISED 1',
    issuer_party_label: null,
    po_version_id: null,
    po_version_no: null,
    extraction_state: 'done',
    document_url: null,
    schedule_date: null,
    phases: [
      {
        id: 'ph1',
        area_group: 'TOWER',
        sequence: 1,
        label: 'Level 2 & 7',
        delivery_date: '2027-01-07',
        promoted_delivery_date: '2026-07-01',
      },
    ],
    products: [
      {
        product_id: 'p1',
        product_code: 'SRTWC8613-RL',
        product_name: 'One-Piece WC',
        customer_code_raw: 'BUI-HB-SRTWC8613-RL',
        resolution_source: 'code',
        column_total: '66',
        reported_total: '66',
        po_qty: '66',
        reconciled: true,
      },
    ],
    cells: [{ phase_id: 'ph1', product_id: 'p1', qty: '66' }],
    reconciliation: { reconciled_columns: 1, total_columns: 1 },
    confirmed_at: null,
    ...overrides,
  };
}

describe('DeliveryScheduleRevisionDiff', () => {
  it('shows the date move as was -> now with a day chip, before the prior version loads', () => {
    render(
      <DeliveryScheduleRevisionDiff version={version()} priorVersion={undefined} priorLoading />,
    );

    expect(screen.getByText('01/07/2026')).toBeInTheDocument();
    expect(screen.getByText('07/01/2027')).toBeInTheDocument();
    expect(screen.getByText('+190 d')).toBeInTheDocument();
    expect(
      screen.getByText('Comparing quantities with the previous version…'),
    ).toBeInTheDocument();
  });

  it('adds the quantity move once the prior version has loaded, and names both in the summary', () => {
    const prior = version({
      id: 'v1',
      version_no: 1,
      phases: [
        {
          id: 'prior-ph1',
          area_group: 'TOWER',
          sequence: 1,
          label: 'Level 2 & 7',
          delivery_date: '2026-07-01',
        },
      ],
      cells: [{ phase_id: 'prior-ph1', product_id: 'p1', qty: '72' }],
    });

    render(
      <DeliveryScheduleRevisionDiff
        version={version()}
        priorVersion={prior}
        priorLoading={false}
      />,
    );

    expect(
      screen.getByText('1 phase moved · 1 quantity changed · 0 unchanged'),
    ).toBeInTheDocument();
    expect(screen.getByText('SRTWC8613-RL qty:')).toBeInTheDocument();
    expect(screen.getByText('72')).toBeInTheDocument();
    expect(screen.getByText('66')).toBeInTheDocument();
  });

  it('says nothing moved when the two versions agree', () => {
    const same = version({
      phases: [
        {
          id: 'ph1',
          area_group: 'TOWER',
          sequence: 1,
          label: 'Level 2 & 7',
          delivery_date: '2026-07-01',
          promoted_delivery_date: '2026-07-01',
        },
      ],
    });
    const prior = version({
      id: 'v1',
      version_no: 1,
      phases: [
        { id: 'prior-ph1', area_group: 'TOWER', sequence: 1, label: 'Level 2 & 7', delivery_date: '2026-07-01' },
      ],
      cells: [{ phase_id: 'prior-ph1', product_id: 'p1', qty: '66' }],
    });

    render(
      <DeliveryScheduleRevisionDiff version={same} priorVersion={prior} priorLoading={false} />,
    );

    expect(
      screen.getByText('0 phases moved · 0 quantities changed · 1 unchanged'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Nothing moved between this version and the one before it.'),
    ).toBeInTheDocument();
  });
});
