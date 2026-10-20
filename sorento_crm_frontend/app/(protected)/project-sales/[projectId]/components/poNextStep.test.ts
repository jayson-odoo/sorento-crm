import { describe, expect, it } from 'vitest';
import { latestVersion, poNextStep } from './poNextStep';

const confirmed = '2026-08-19T00:00:00';

describe('poNextStep (PM-SIMPLIFY AC-P2)', () => {
  it('walks Confirm PO, Upload schedule, Confirm schedule, Build, Publish, then nothing', () => {
    const base = { hasLines: true, salesOrderStatuses: [] as string[] };
    expect(
      poNextStep({ ...base, poVersions: [{ id: 'p1', version_no: 1 }], scheduleVersions: [] }),
    ).toMatchObject({ kind: 'confirm-po', versionId: 'p1', label: 'Confirm PO' });

    const po = [{ id: 'p1', version_no: 1, confirmed_at: confirmed }];
    expect(poNextStep({ ...base, poVersions: po, scheduleVersions: [] }).kind).toBe(
      'upload-schedule',
    );
    expect(
      poNextStep({ ...base, poVersions: po, scheduleVersions: [{ id: 's1', version_no: 1 }] }),
    ).toMatchObject({ kind: 'confirm-schedule', versionId: 's1' });

    const schedule = [{ id: 's1', version_no: 1, confirmed_at: confirmed }];
    expect(poNextStep({ ...base, poVersions: po, scheduleVersions: schedule })).toMatchObject({
      kind: 'build',
      scheduleVersionId: 's1',
    });
    expect(
      poNextStep({
        hasLines: true,
        poVersions: po,
        scheduleVersions: schedule,
        salesOrderStatuses: ['draft', 'blocked', 'published'],
      }),
    ).toMatchObject({ kind: 'publish', count: 2, label: 'Publish 2 sales orders' });
    expect(
      poNextStep({
        hasLines: true,
        poVersions: po,
        scheduleVersions: schedule,
        salesOrderStatuses: ['published', 'amended'],
      }).kind,
    ).toBe('none');
  });

  it('asks to confirm a newer unconfirmed version even when an older one is confirmed', () => {
    expect(
      poNextStep({
        hasLines: true,
        salesOrderStatuses: [],
        poVersions: [
          { id: 'p1', version_no: 1, confirmed_at: confirmed },
          { id: 'p2', version_no: 2 },
        ],
        scheduleVersions: [],
      }),
    ).toMatchObject({ kind: 'confirm-po', versionId: 'p2' });
  });

  it('lets a hand-keyed PO (no document) go straight to its schedule, and waits for lines', () => {
    expect(
      poNextStep({ hasLines: true, poVersions: [], scheduleVersions: [], salesOrderStatuses: [] })
        .kind,
    ).toBe('upload-schedule');
    expect(
      poNextStep({ hasLines: false, poVersions: [], scheduleVersions: [], salesOrderStatuses: [] })
        .kind,
    ).toBe('none');
  });

  it('takes the newest upload as the latest version, across two schedules', () => {
    expect(
      latestVersion([
        { id: 'a', version_no: 2, created_at: '2026-03-04T00:00:00' },
        { id: 'b', version_no: 1, created_at: '2026-07-23T00:00:00' },
      ])?.id,
    ).toBe('b');
  });
});
