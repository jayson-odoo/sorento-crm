import type { PartyType } from '../../_shared/types/project.types';

/**
 * The five kinds of organisation a project references, with the one sentence that
 * explains why each is a party rather than a customer.
 *
 * Shared by the list filter, the create/edit form and the detail page so a type can
 * never be spelled one way in a picker and another way in a table.
 */
export const PARTY_TYPE_OPTIONS: { value: PartyType; label: string; hint: string }[] = [
  {
    value: 'developer',
    label: 'Developer',
    hint: 'Owns the development. Identity for the registration lock.',
  },
  {
    value: 'architect',
    label: 'Architect',
    hint: 'Specifies products. Never buys, which is why they are not a customer.',
  },
  { value: 'main_contractor', label: 'Main contractor', hint: 'Builds it.' },
  { value: 'trading_house', label: 'Trading house', hint: 'Buys on the project’s behalf.' },
  { value: 'consultant', label: 'Consultant', hint: 'QS, M&E, ID and similar.' },
];

export const TYPE_LABEL: Record<string, string> = Object.fromEntries(
  PARTY_TYPE_OPTIONS.map((option) => [option.value, option.label]),
);

export const TYPE_HINT: Record<string, string> = Object.fromEntries(
  PARTY_TYPE_OPTIONS.map((option) => [option.value, option.hint]),
);
