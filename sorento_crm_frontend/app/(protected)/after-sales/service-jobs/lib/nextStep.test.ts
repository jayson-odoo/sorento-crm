/**
 * AFTER-SALES-P1 red tests (UAC D3, D2): the one filled button per status, and the moves a
 * status still allows (gear menu and right-click menu).
 *
 * Contract: `./nextStep` exports
 *   nextStepFor(job: { status: ServiceJobStatus; technician_id: string | null })
 *     -> { action: 'confirm' | 'assign' | 'on_the_way' | 'arrived' | 'completed' | 'verified'; label: string } | null
 *   secondaryMoves(status: ServiceJobStatus) -> Array<{ to: ServiceJobStatus; label: string; needsReason: boolean }>
 */
import { describe, it, expect } from 'vitest';

import { nextStepFor, secondaryMoves } from './nextStep';

describe('nextStepFor (D3)', () => {
  it.each([
    ['proposed', null, 'confirm', 'Confirm date'],
    ['confirmed', null, 'assign', 'Assign technician'],
    ['confirmed', 'tech-1', 'on_the_way', 'On the way'],
    ['on_the_way', 'tech-1', 'arrived', 'Arrived'],
    ['arrived', 'tech-1', 'completed', 'Complete'],
    ['completed', 'tech-1', 'verified', 'Verify'],
  ] as const)('%s with technician %s -> %s', (status, technician_id, action, label) => {
    expect(nextStepFor({ status, technician_id })).toEqual({ action, label });
  });

  it.each(['verified', 'cancelled'] as const)('%s has no next step', (status) => {
    expect(nextStepFor({ status, technician_id: 'tech-1' })).toBeNull();
  });
});

describe('secondaryMoves (gear menu / right-click)', () => {
  const to = (s: Parameters<typeof secondaryMoves>[0]) => secondaryMoves(s).map((m) => m.to).sort();

  it('lists exactly the graph moves that are not the main step', () => {
    expect(to('proposed')).toEqual(['cancelled']);
    expect(to('confirmed')).toEqual(['arrived', 'cancelled', 'proposed']);
    expect(to('on_the_way')).toEqual(['proposed']);
    expect(to('arrived')).toEqual(['proposed']);
    expect(to('completed')).toEqual(['arrived']);
    expect(to('verified')).toEqual([]);
    expect(to('cancelled')).toEqual([]);
  });

  it('labels the reasoned moves as the graph does and flags the reason', () => {
    const byTo = (s: Parameters<typeof secondaryMoves>[0], t: string) => secondaryMoves(s).find((m) => m.to === t)!;
    expect(byTo('confirmed', 'proposed')).toMatchObject({ label: 'Customer rejected the visit', needsReason: true });
    expect(byTo('arrived', 'proposed')).toMatchObject({ label: 'Revisit needed', needsReason: true });
    expect(byTo('completed', 'arrived')).toMatchObject({ label: 'Reopen: work not accepted', needsReason: false });
    expect(byTo('proposed', 'cancelled')).toMatchObject({ label: 'Cancel', needsReason: true });
  });
});

describe('secondaryMoves without a technician (fix round 1, S-9)', () => {
  it('never offers Arrived while no technician is assigned', () => {
    expect(secondaryMoves('confirmed', false).map((m) => m.to).sort()).toEqual(['cancelled', 'proposed']);
    expect(secondaryMoves('confirmed', true).map((m) => m.to)).toContain('arrived');
    expect(secondaryMoves('completed', false).map((m) => m.to)).toEqual(['arrived']);
  });
});
