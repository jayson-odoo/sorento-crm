/**
 * One pasted flyer card carrying every state the review has to render, for the
 * Phase 1 prototype and for the component tests that outlive it.
 *
 * Every case named in the plan is here on purpose:
 *
 *  - a `new` key the product says nothing about
 *  - a `change` over a machine reading, which is ticked by default
 *  - a `conflict` over a value a person set, which is NOT
 *  - a numeric value with a unit and a boolean, so the readable-value path is exercised
 *  - a result with no proposals at all and a non-zero `unchanged` count, which is
 *    what a flyer restating the description produces and is the common case
 *  - a result read by the rules alone, with no model reachable
 */
import type { SpecProposal } from '../types';

/** The three kinds on one product, in the order the review lists them. */
export const MOCK_PROPOSALS: SpecProposal[] = [
  {
    spec_key: 'seat_material',
    label: 'Seat cover material',
    data_type: 'text',
    value: 'pp',
    unit: null,
    evidence: '*PP Seat Cover',
    kind: 'new',
    stored_value: null,
    stored_unit: null,
    stored_source: null,
  },
  {
    spec_key: 'dim_height',
    label: 'Height',
    data_type: 'numeric',
    value: 770,
    unit: 'mm',
    evidence: 'D: L680xW375xH770mm',
    kind: 'change',
    stored_value: 750,
    stored_unit: 'mm',
    stored_source: 'derived',
  },
  {
    spec_key: 'is_rimless',
    label: 'Rimless',
    data_type: 'boolean',
    value: true,
    unit: null,
    evidence: 'Washdown With Rimless',
    kind: 'new',
    stored_value: null,
    stored_unit: null,
    stored_source: null,
  },
  {
    spec_key: 'finish',
    label: 'Finish or colour',
    data_type: 'text',
    value: 'matt_black',
    unit: null,
    evidence: 'Matt Black finish',
    kind: 'conflict',
    stored_value: 'chrome',
    stored_unit: null,
    stored_source: 'human',
  },
];

/** The keys the text merely restated. Counted, never listed (AC-B.3). */
export const MOCK_UNCHANGED = 3;

/** Every key a supplier text proposes is already what the product says. */
export const MOCK_PROPOSALS_NONE: SpecProposal[] = [];
