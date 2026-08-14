/**
 * Phase 1 fixtures: the PHONE LIST workbook as the design report described it.
 *
 * 18 people across 4 department sections, with the data-quality facts that were
 * actually observed in the file baked in so the prototype is exercised against
 * them rather than against tidy data:
 *
 * - dashed Malaysian mobile numbers (`01X-XXXXXXX`),
 * - email addresses carrying trailing whitespace,
 * - one row with no email at all,
 * - one row whose phone cannot be read.
 *
 * Deleted in Phase 2 except where a test still uses them.
 */

import type {
  OnboardingIntakeContext,
  OnboardingPerson,
  OnboardingTemplateOption,
} from '@/components/common/onboarding/types';

export const MOCK_TEMPLATES: OnboardingTemplateOption[] = [
  {
    id: 'tpl-salesperson',
    name: 'Salesperson',
    description: 'Sees their own orders and customers, and is reachable on WhatsApp.',
    default_needs_system_account: true,
    default_needs_respond_contact: true,
    default_needs_agent_seat: false,
  },
  {
    id: 'tpl-sales-admin',
    name: 'Sales admin',
    description: 'Office staff who key in and chase orders.',
    default_needs_system_account: true,
    default_needs_respond_contact: true,
    default_needs_agent_seat: true,
  },
  {
    id: 'tpl-warehouse',
    name: 'Warehouse',
    description: 'Stock movements and delivery orders only.',
    default_needs_system_account: true,
    default_needs_respond_contact: false,
    default_needs_agent_seat: false,
  },
  {
    id: 'tpl-dealer',
    name: 'Dealer',
    description: 'Reachable on WhatsApp. No system login.',
    default_needs_system_account: false,
    default_needs_respond_contact: true,
    default_needs_agent_seat: false,
  },
];

type Seed = {
  name: string;
  nick: string;
  phone: string;
  email: string | null;
  section: string;
  template: string;
  problems?: string[];
};

const SEEDS: Seed[] = [
  { name: 'Nurul Aisyah binti Rahman', nick: 'Aisyah', phone: '012-3456781', email: 'aisyah@mocha.com.my ', section: 'SALES PERSON', template: 'tpl-salesperson' },
  { name: 'Tan Wei Ming', nick: 'Wei', phone: '012-3456782', email: 'weiming@mocha.com.my', section: 'SALES PERSON', template: 'tpl-salesperson' },
  { name: 'Kavitha Subramaniam', nick: 'Kavi', phone: '013-3456783', email: 'kavitha@mocha.com.my ', section: 'SALES PERSON', template: 'tpl-salesperson' },
  { name: 'Mohd Faizal bin Osman', nick: 'Faizal', phone: '011-23456784', email: 'faizal@mocha.com.my', section: 'SALES PERSON', template: 'tpl-salesperson' },
  { name: 'Lim Siew Peng', nick: 'Siew', phone: '016-3456785', email: 'siewpeng@mocha.com.my', section: 'SALES PERSON', template: 'tpl-salesperson' },
  { name: 'Ahmad Zulkifli bin Hashim', nick: 'Zul', phone: '017-3456786', email: null, section: 'SALES PERSON', template: 'tpl-salesperson', problems: ['no email'] },
  { name: 'Priya Devi Ramasamy', nick: 'Priya', phone: '019-3456787', email: 'priya@mocha.com.my ', section: 'SALES PERSON', template: 'tpl-salesperson' },
  { name: 'Chong Kah Wai', nick: 'Kah Wai', phone: '012-3456788', email: 'kahwai@mocha.com.my', section: 'SALES PERSON', template: 'tpl-salesperson' },

  { name: 'Siti Nurhaliza binti Yusof', nick: 'Siti', phone: '012-3456789', email: 'siti@mocha.com.my', section: 'SALES ADMIN', template: 'tpl-sales-admin' },
  { name: 'Ng Mei Ling', nick: 'Mei', phone: '013-3456790', email: 'meiling@mocha.com.my ', section: 'SALES ADMIN', template: 'tpl-sales-admin' },
  { name: 'Rajesh Kumar Nair', nick: 'Raj', phone: '01x-345679', email: 'rajesh@mocha.com.my', section: 'SALES ADMIN', template: 'tpl-sales-admin', problems: ['phone not recognised'] },
  { name: 'Farah Nabila binti Idris', nick: 'Farah', phone: '016-3456792', email: 'farah@mocha.com.my', section: 'SALES ADMIN', template: 'tpl-sales-admin' },
  { name: 'Wong Chee Keong', nick: 'CK', phone: '017-3456793', email: 'cheekeong@mocha.com.my ', section: 'SALES ADMIN', template: 'tpl-sales-admin' },
  { name: 'Nur Amirah binti Salleh', nick: 'Amirah', phone: '019-3456794', email: 'amirah@mocha.com.my', section: 'SALES ADMIN', template: 'tpl-sales-admin' },

  { name: 'Hassan bin Ibrahim', nick: 'Hassan', phone: '012-3456795', email: 'hassan@mocha.com.my', section: 'WAREHOUSE', template: 'tpl-warehouse' },
  { name: 'Goh Beng Huat', nick: 'Beng', phone: '013-3456796', email: 'benghuat@mocha.com.my ', section: 'WAREHOUSE', template: 'tpl-warehouse' },

  { name: 'Suresh Manickam', nick: 'Suresh', phone: '016-3456797', email: 'suresh@mocha.com.my', section: 'SERVICES/REPLACEMENT', template: 'tpl-warehouse' },
  { name: 'Azlan bin Mokhtar', nick: 'Azlan', phone: '017-3456798', email: 'azlan@mocha.com.my', section: 'SERVICES/REPLACEMENT', template: 'tpl-warehouse' },
];

function toPerson(seed: Seed, index: number): OnboardingPerson {
  const template = MOCK_TEMPLATES.find((t) => t.id === seed.template)!;
  return {
    id: `person-${index + 1}`,
    row_number: index + 1,
    full_name: seed.name,
    nick_name: seed.nick,
    phone_raw: seed.phone,
    email_raw: seed.email,
    section_label: seed.section,
    template_id: template.id,
    requester_note: null,
    reviewer_note: null,
    needs_system_account: template.default_needs_system_account,
    needs_respond_contact: template.default_needs_respond_contact,
    needs_agent_seat: template.default_needs_agent_seat,
    review_status: 'proposed',
    rejection_reason: null,
    problems: seed.problems ?? [],
    collisions: [],
    user_step: 'pending',
    user_error: null,
    user_label: null,
    contact_step: 'pending',
    contact_error: null,
    agent_step: 'pending',
    agent_error: null,
  };
}

export const MOCK_PEOPLE: OnboardingPerson[] = SEEDS.map(toPerson);

/** The requester's view before she has submitted. */
export const MOCK_INTAKE_CONTEXT: OnboardingIntakeContext = {
  title: 'MOCHA staff onboarding',
  company_name: 'MOCHA Sdn Bhd',
  requester_name: 'Esther Lim',
  requester_email: 'esther@mocha.com.my',
  status: 'sent',
  expires_at: '2026-08-28T09:00:00',
  editable: true,
  requester_note: null,
  templates: MOCK_TEMPLATES,
  people: [],
};

/** What the parse endpoint would answer for the PHONE LIST workbook. */
export const MOCK_PARSE_RESULT = {
  rows: SEEDS.map((seed, index) => ({
    row_number: index + 1,
    full_name: seed.name,
    nick_name: seed.nick,
    phone_raw: seed.phone,
    email_raw: seed.email,
    section_label: seed.section,
    problems: seed.problems ?? [],
  })),
  problems: [],
  unmapped_headers: [],
  missing_columns: [],
  total_rows: SEEDS.length,
  sections: ['SALES PERSON', 'SALES ADMIN', 'WAREHOUSE', 'SERVICES/REPLACEMENT'],
};
