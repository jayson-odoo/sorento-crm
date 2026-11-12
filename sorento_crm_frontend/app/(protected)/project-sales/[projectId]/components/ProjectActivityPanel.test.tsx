/**
 * QUOTE-DUPLICATE-PARTY crew pass (step 13): the Activity tab shows the copy and the carried
 * approval as the sentences the server saved, and never an internal key. Names are invented.
 */
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/components/common/ActivitiesNotesPanel/activitiesPanelService', () => ({
  listActivities: async () => ({
    items: [
      {
        id: 'a2', kind: 'system', system_template: 'quotation_approval_carried', system_payload: {},
        body_text: 'Test Person carried the approval of PRJQ-2026-0003 to PRJQ-2026-0009',
        created_at: '2026-11-11T08:00:01', actor: { name: 'Test Person' },
      },
      {
        id: 'a1', kind: 'system', system_template: 'quotation_created', system_payload: {},
        body_text: 'PRJQ-2026-0009 copied from PRJQ-2026-0003 for ARKITEK CONTOH',
        created_at: '2026-11-11T08:00:00', actor: { name: 'Test Person' },
      },
      {
        id: 'a0', kind: 'system', system_template: 'quotation_created', system_payload: {},
        body_text: null, created_at: '2026-11-10T08:00:00', actor: { name: 'Test Person' },
      },
    ],
  }),
}));

import { ProjectActivityPanel } from './ProjectActivityPanel';

afterEach(cleanup);

describe('ProjectActivityPanel', () => {
  it('shows the saved sentences, the plain label otherwise, and no raw key', async () => {
    render(<ProjectActivityPanel project={{ id: 'p1' } as never} />);
    expect(await screen.findByText('PRJQ-2026-0009 copied from PRJQ-2026-0003 for ARKITEK CONTOH')).toBeTruthy();
    expect(screen.getByText('Test Person carried the approval of PRJQ-2026-0003 to PRJQ-2026-0009')).toBeTruthy();
    expect(screen.getByText('Quotation created')).toBeTruthy();
    expect(screen.queryByText(/quotation_/)).toBeNull();
  });
});
