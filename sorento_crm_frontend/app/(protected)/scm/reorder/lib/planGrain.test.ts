/**
 * Plan grain - the run's stamped decision grain (plan section 5.1, AC-F01 / AC-F09
 * / AC-F10).
 *
 * Three states pinned here, and the third is deliberately not a value of the
 * first two:
 *
 * - `product` - the Product decision surface is open; Location reads a lock.
 * - `location` - the reverse.
 * - LEGACY   - identified by a NULL `front_planning_contract_version`, not by
 *    a missing grain alone (a legacy run also carries no `decision_grain`, but
 *    the contract version is the field that decides it). Read-only in both
 *    grains, and never backfilled.
 */
import { describe, it, expect } from 'vitest';
import {
  decisionLockReason,
  isLegacyRun,
  legacyLockReason,
  planGrainLabel,
  type RunGrainState,
} from './planGrain';

const PRODUCT_RUN: RunGrainState = { decision_grain: 'product', front_planning_contract_version: 1 };
const LOCATION_RUN: RunGrainState = { decision_grain: 'location', front_planning_contract_version: 1 };
const LEGACY_RUN: RunGrainState = { decision_grain: null, front_planning_contract_version: null };

describe('isLegacyRun', () => {
  it('is false for a run with a stamped grain and contract version 1', () => {
    expect(isLegacyRun(PRODUCT_RUN)).toBe(false);
    expect(isLegacyRun(LOCATION_RUN)).toBe(false);
  });

  it('is true for a run whose contract version is null, even if a grain is present', () => {
    expect(isLegacyRun({ decision_grain: 'product', front_planning_contract_version: null })).toBe(
      true,
    );
  });

  it('is true for a run whose contract version is undefined', () => {
    expect(isLegacyRun({ decision_grain: 'product' })).toBe(true);
  });

  it('is true when the grain is missing even though a contract version is present', () => {
    // Defensive: a stamped run always carries both fields together, but the grain
    // absence alone must still read as legacy rather than crash on a null grain.
    expect(isLegacyRun({ decision_grain: null, front_planning_contract_version: 1 })).toBe(true);
  });

  it('is false for a null or undefined run - "unknown" is not "legacy"', () => {
    expect(isLegacyRun(null)).toBe(false);
    expect(isLegacyRun(undefined)).toBe(false);
  });

  it('is true for the canonical legacy shape', () => {
    expect(isLegacyRun(LEGACY_RUN)).toBe(true);
  });
});

describe('planGrainLabel', () => {
  it('states the run has no grain yet when the run itself is not loaded', () => {
    expect(planGrainLabel(null)).toBe('Plan grain unknown');
    expect(planGrainLabel(undefined)).toBe('Plan grain unknown');
  });

  it('labels a Product-grain run', () => {
    expect(planGrainLabel(PRODUCT_RUN)).toBe('Plan grain: Product');
  });

  it('labels a Location-grain run', () => {
    expect(planGrainLabel(LOCATION_RUN)).toBe('Plan grain: Location');
  });

  it('labels a legacy run as "Legacy run", never as an absent grain', () => {
    expect(planGrainLabel(LEGACY_RUN)).toBe('Legacy run');
  });
});

describe('decisionLockReason', () => {
  it('is null (actionable) when the run is not loaded yet', () => {
    expect(decisionLockReason(null, 'product')).toBeNull();
    expect(decisionLockReason(undefined, 'location')).toBeNull();
  });

  it('is null when the surface matches the run stamped grain', () => {
    expect(decisionLockReason(PRODUCT_RUN, 'product')).toBeNull();
    expect(decisionLockReason(LOCATION_RUN, 'location')).toBeNull();
  });

  it('names Product as the owning screen when a Location surface reads a Product-grain run', () => {
    expect(decisionLockReason(PRODUCT_RUN, 'location')).toBe('Decided at Product grain');
  });

  it('names Location as the owning screen when a Product surface reads a Location-grain run', () => {
    expect(decisionLockReason(LOCATION_RUN, 'product')).toBe('Decided at Location grain');
  });

  it('locks BOTH surfaces on a legacy run, with its own reason', () => {
    expect(decisionLockReason(LEGACY_RUN, 'product')).toBe(
      'Legacy run - read only. Create a new plan to decide.',
    );
    expect(decisionLockReason(LEGACY_RUN, 'location')).toBe(
      'Legacy run - read only. Create a new plan to decide.',
    );
  });

  it('checks legacy before grain-mismatch, so a legacy run never falls through to the grain message', () => {
    // A run with no grain and no contract version could otherwise read as a
    // "decided at the other (null) grain" mismatch instead of "legacy".
    const reason = decisionLockReason(LEGACY_RUN, 'product');
    expect(reason).not.toMatch(/Decided at/);
  });
});

/**
 * S16 (captain, 21 Aug, 3rd time requested): "I want the decision made here" - the
 * reorder plan row's OWN lock. Unlike `decisionLockReason` (still the Order summary
 * sheet's own grain-scoped lock, unchanged above), the plan row is a decision surface at
 * EVERY grain now - the only thing that still locks it is a run that predates the
 * front-planning contract.
 */
describe('legacyLockReason', () => {
  it('is null (actionable) when the run is not loaded yet', () => {
    expect(legacyLockReason(null)).toBeNull();
    expect(legacyLockReason(undefined)).toBeNull();
  });

  it('is null for BOTH grains of a front-planning run - grain no longer locks the row', () => {
    expect(legacyLockReason(PRODUCT_RUN)).toBeNull();
    expect(legacyLockReason(LOCATION_RUN)).toBeNull();
  });

  it('locks a legacy run, with the same wording decisionLockReason uses for it', () => {
    expect(legacyLockReason(LEGACY_RUN)).toBe(
      'Legacy run - read only. Create a new plan to decide.',
    );
  });
});
