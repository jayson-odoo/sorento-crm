/**
 * ============================================================================
 * Warranty configuration - DETERMINISTIC MOCK BACKING STORE  (Phase 1 only)
 * ============================================================================
 * PROTOTYPE DATA. No network, no `Math.random`. Every value below is a
 * transcription of the DEV DATABASE as measured on 2026-08-09, because the whole
 * point of this screen is a proportion:
 *
 *     31 Kinds - 41 Terms - 2 Kind Rules - 29 Kinds no rule can reach
 *     1 Policy (v15, effective 2000-01-01, open ended) - 23 assessments
 *
 * A tidy mock where every Kind has a rule would hide exactly the hole the slice
 * exists to make visible, so the seed is the real thing, warts included.
 *
 * TWO deliberate departures from the measured data, both so a state is
 * reachable in the prototype at all:
 *  1. `assessment_count` is 0 on every Term except the three under the two
 *     RULE-REACHABLE Kinds (mirror_cabinet, bathroom_furniture). Measured, all 23
 *     live assessments have `term_id IS NULL` - they are `no_term` verdicts,
 *     which is the same finding from the other end. Without a non-zero somewhere
 *     the AC-P8a confirmation copy has only one branch to show.
 *  2. `?mock=` on the URL selects a scenario (`empty`, `error`, `slow`) so the
 *     loading / empty / error states can be exercised in a browser without
 *     editing this file. No UI affordance exists for it and Phase 2 deletes it
 *     with the rest of the file.
 *
 * Phase 2 flips `USE_WARRANTY_CONFIG_MOCKS` in
 * `services/warrantyConfigService.ts` and deletes this module; every function
 * here already has its real `apiFetch` counterpart wired to the same contract.
 *
 * The `testKindRules` mock MIRRORS the production ranking
 * (`_matched_length` + `_RuleMatch.sort_key` in
 * `app/services/warranty_service.py`) but is NOT it. Phase 2's tester calls
 * `resolve_kind_match()` verbatim (AC-P6a) - a tester with its own ranking
 * agrees with production right up to the day it matters.
 * ============================================================================
 */
import type {
  DefectTypeOption,
  KindRuleMatchType,
  KindRuleTestMatch,
  KindRuleTestRequest,
  KindRuleTestResponse,
  SupersedeResult,
  TestedRule,
  WarrantyKindRef,
  WarrantyKindRow,
  WarrantyKindRuleRow,
  WarrantyKindRuleWrite,
  WarrantyKindWrite,
  WarrantyPolicyRow,
  WarrantyPolicyWrite,
  WarrantyTermRow,
  WarrantyTermWrite,
  WarrantyTermsGrouped,
} from '../types/warranty-config.types';

// ── Scenario switch (Phase-1 only, see header) ──────────────────────────────

type MockScenario = 'default' | 'empty' | 'error' | 'slow';

function scenario(): MockScenario {
  if (typeof window === 'undefined') return 'default';
  const raw = new URLSearchParams(window.location.search).get('mock');
  if (raw === 'empty' || raw === 'error' || raw === 'slow') return raw;
  return 'default';
}

const LATENCY_MS = 180;

async function settle<T>(value: () => T): Promise<T> {
  const mode = scenario();
  await new Promise((r) => setTimeout(r, mode === 'slow' ? 60_000 : LATENCY_MS));
  if (mode === 'error') {
    throw new Error('Warranty configuration is unavailable right now. Try again.');
  }
  return value();
}

function isEmptyScenario(): boolean {
  return scenario() === 'empty';
}

// ── Defect types (`complaints_defect_type` lookup options) ──────────────────

const DEFECT_TYPES: DefectTypeOption[] = [
  { id: 'dft-crack-line', label: 'Crack Line' },
  { id: 'dft-leakage', label: 'Leakage' },
  { id: 'dft-rust', label: 'Rust' },
  { id: 'dft-holder-broken', label: 'Holder Broken' },
];

const CRACK_AND_LEAK = ['dft-crack-line', 'dft-leakage'];

// ── Kinds (all 31, in the seed's sort order) ────────────────────────────────

interface KindSeed {
  code: string;
  name: string;
  consumer_label: string;
}

const KIND_SEED: KindSeed[] = [
  { code: 'water_closet', name: 'Water Closet', consumer_label: 'Water Closet' },
  { code: 'urinal_bowl', name: 'Urinal Bowl', consumer_label: 'Urinal Bowl' },
  { code: 'squatting_pan', name: 'Squatting Pan', consumer_label: 'Squatting Pan' },
  { code: 'electronic_seat_cover', name: 'Electronic Seat Cover', consumer_label: 'Electronic Seat Cover' },
  { code: 'intelligent_water_closet', name: 'Intelligent Water Closet', consumer_label: 'Intelligent Water Closet' },
  { code: 'tankless_water_closet', name: 'Tankless Water Closet', consumer_label: 'Tankless Water Closet' },
  { code: 'wash_basin', name: 'Wash Basin', consumer_label: 'Wash Basin' },
  { code: 'led_mirror', name: 'LED Mirror', consumer_label: 'LED Mirror' },
  { code: 'bathroom_furniture', name: 'Bathroom Furniture', consumer_label: 'Bathroom Furniture' },
  { code: 'mirror_cabinet', name: 'Mirror Cabinet', consumer_label: 'Mirror Cabinet' },
  { code: 'concealed_shower_mixer_cold', name: 'Concealed Shower Mixer & Cold', consumer_label: 'Concealed Shower Mixer & Cold' },
  { code: 'kitchen_bathroom_cold_tap', name: 'Kitchen & Bathroom Cold Tap', consumer_label: 'Kitchen & Bathroom Cold Tap' },
  { code: 'stop_valve', name: 'Stop Valve', consumer_label: 'Stop Valve' },
  { code: 'bib_hose_two_way_tap_bidet_set', name: 'Bib Tap, Hose Bib Tap, Two Way Tap and Two Way Bidet Set', consumer_label: 'Bib Tap, Hose Bib Tap, Two Way Tap and Two Way Bidet Set' },
  { code: 'exposed_mixer_shower_set', name: 'Exposed Mixer Shower Set', consumer_label: 'Exposed Mixer Shower Set' },
  { code: 'conceal_bath_shower_mixer', name: 'Conceal Bath and Shower Mixer', consumer_label: 'Conceal Bath and Shower Mixer' },
  { code: 'conceal_bathroom_mixer', name: 'Conceal Bathroom Mixer', consumer_label: 'Conceal Bathroom Mixer' },
  { code: 'kitchen_bathroom_mixer_tap', name: 'Kitchen & Bathroom Mixer Tap', consumer_label: 'Kitchen & Bathroom Mixer Tap' },
  { code: 'exposed_shower_set', name: 'Exposed Shower Set', consumer_label: 'Exposed Shower Set' },
  { code: 'bathtub_massage_jet', name: 'Bathtub with Massage jet', consumer_label: 'Bathtub with Massage Jet' },
  { code: 'kitchen_sink_ss304', name: 'Stainless Steel 304 Kitchen Sink', consumer_label: 'Kitchen Sink' },
  { code: 'ceramic_kitchen_sink', name: 'Ceramic Kitchen Sink', consumer_label: 'Ceramic Kitchen Sink' },
  { code: 'kitchen_bathroom_tap_ss304', name: 'Stainless Steel 304 Kitchen and Bathroom Tap', consumer_label: 'Stainless Steel 304 Kitchen and Bathroom Tap' },
  { code: 'kitchen_mixer_cold_tap', name: 'Kitchen Mixer & Cold Tap', consumer_label: 'Kitchen Mixer & Cold Tap' },
  { code: 'kitchen_mixer_tap', name: 'Kitchen Mixer Tap', consumer_label: 'Kitchen Mixer Tap' },
  { code: 'booster_pump', name: 'Automatic Water Booster Pump', consumer_label: 'Automatic Water Booster Pump' },
  { code: 'hand_shower', name: 'Hand Shower', consumer_label: 'Hand Shower' },
  { code: 'hand_bidet', name: 'Hand Bidet', consumer_label: 'Hand Bidet' },
  { code: 'flush_valves_concealed_cistern', name: 'Exposed and Conceal Flush Valves, Concealed Cistern', consumer_label: 'Flush Valves and Concealed Cistern' },
  { code: 'sensor_tap', name: 'Sensor Taps', consumer_label: 'Sensor Taps' },
  { code: 'self_closing_tap', name: 'Self-Closing Tap', consumer_label: 'Self-Closing Tap' },
];

const kindId = (code: string) => `kind-${code}`;

let kinds: WarrantyKindRow[] = KIND_SEED.map((k, i) => ({
  id: kindId(k.code),
  code: k.code,
  name: k.name,
  consumer_label: k.consumer_label,
  consumer_icon: null,
  sort_order: i + 1,
  is_active: true,
  rule_count: 0,
  term_count: 0,
  has_no_rules: true,
  has_no_terms: true,
}));

// ── The one policy ──────────────────────────────────────────────────────────

const POLICY_TEXT_V15 = [
  'SORENTO WARRANTY POLICY (Version 15)',
  '',
  'Clause 3(b): Online registration extends, and is never a precondition of, cover.',
  'Clause 15: Where installation is included, the callout is at Sorento’s cost.',
  'Clause 16: Sorento may amend this document without notice; a claim is judged',
  'against the version in force on the purchase date.',
  'Clause 17: Cover is restricted to residential installations. Commercial and',
  'industrial installations are excluded.',
  'Clause 26: The Automatic Water Booster Pump carries 2 years, extended to 3 with',
  'online registration.',
].join('\n');

let policies: WarrantyPolicyRow[] = [
  {
    id: 'pol-v15',
    version: 'v15',
    effective_from: '2000-01-01',
    effective_to: null,
    policy_text: POLICY_TEXT_V15,
    source_attachment_name: null,
    term_count: 0,
    created_at: '2026-07-14T09:12:00',
    updated_at: null,
  },
];

// ── Terms (all 41, verbatim) ────────────────────────────────────────────────

const INSTALL_INCLUDED = 'Installation is included.';
const INSTALL_EXCLUDED = 'Installation is excluded.';
const CERAMIC_QUAL = `Lifetime Warranty on crack line and leaking ONLY. ${INSTALL_INCLUDED}`;
const CERAMIC_EXCL = 'Any crack line caused by external force and/or willful act is excluded.';

interface TermSeed {
  kind: string;
  part: string;
  months: number | null;
  lifetime: boolean;
  install: boolean;
  bonus?: number | null;
  defects?: string[] | null;
  qual?: string | null;
  excl?: string | null;
  assessments?: number;
}

const ceramicBody = (kind: string): TermSeed => ({
  kind,
  part: 'Ceramic Body',
  months: null,
  lifetime: true,
  install: true,
  defects: CRACK_AND_LEAK,
  qual: CERAMIC_QUAL,
  excl: CERAMIC_EXCL,
});

const cartridge = (kind: string, months: number): TermSeed => ({
  kind,
  part: 'Cartridge',
  months,
  lifetime: false,
  install: false,
  qual: INSTALL_EXCLUDED,
});

const TERM_SEED: TermSeed[] = [
  // Water Closet - the AC-P4 case: three simultaneous Terms that disagree on
  // duration, defect scope, installation and lifetime.
  ceramicBody('water_closet'),
  { kind: 'water_closet', part: 'Flushing Fittings', months: 60, lifetime: false, install: false, qual: INSTALL_EXCLUDED },
  { kind: 'water_closet', part: 'Seat Cover Soft Close', months: 24, lifetime: false, install: false, qual: INSTALL_EXCLUDED },

  ceramicBody('urinal_bowl'),
  ceramicBody('squatting_pan'),
  { kind: 'electronic_seat_cover', part: 'Electronic Components', months: 12, lifetime: false, install: true, qual: INSTALL_INCLUDED },
  ceramicBody('intelligent_water_closet'),
  { kind: 'intelligent_water_closet', part: 'Electronic Components', months: 12, lifetime: false, install: true, qual: INSTALL_INCLUDED },
  ceramicBody('tankless_water_closet'),
  { kind: 'tankless_water_closet', part: 'Flushing Fittings', months: 24, lifetime: false, install: true, qual: INSTALL_INCLUDED },
  ceramicBody('wash_basin'),
  { kind: 'led_mirror', part: 'Circuit Board', months: 12, lifetime: false, install: true, qual: INSTALL_INCLUDED },
  { kind: 'bathroom_furniture', part: 'External Surface Coating', months: 120, lifetime: false, install: false, qual: `Selected Models: *Honeycomb Series. ${INSTALL_EXCLUDED}`, assessments: 1 },
  { kind: 'mirror_cabinet', part: 'Aluminum Frame', months: 120, lifetime: false, install: true, qual: `Selected Models only. ${INSTALL_INCLUDED}` },
  { kind: 'mirror_cabinet', part: 'Hinges', months: 300, lifetime: false, install: true, qual: `Selected Models only. ${INSTALL_INCLUDED}` },
  { kind: 'mirror_cabinet', part: 'Mirror Glass', months: 24, lifetime: false, install: true, qual: `Selected Models only. ${INSTALL_INCLUDED}`, assessments: 2 },
  cartridge('concealed_shower_mixer_cold', 60),
  cartridge('kitchen_bathroom_cold_tap', 60),
  cartridge('stop_valve', 60),
  cartridge('bib_hose_two_way_tap_bidet_set', 60),
  cartridge('exposed_mixer_shower_set', 120),
  cartridge('conceal_bath_shower_mixer', 120),
  cartridge('conceal_bathroom_mixer', 120),
  cartridge('kitchen_bathroom_mixer_tap', 120),
  { kind: 'exposed_shower_set', part: 'Diverter Cartridge', months: 60, lifetime: false, install: false, qual: INSTALL_EXCLUDED },
  { kind: 'bathtub_massage_jet', part: 'Digital Control Panel', months: 12, lifetime: false, install: true, qual: INSTALL_INCLUDED },
  { kind: 'bathtub_massage_jet', part: 'Mixer Tap Cartridge', months: 60, lifetime: false, install: true, qual: INSTALL_INCLUDED },
  { kind: 'bathtub_massage_jet', part: 'Thermostat Heater', months: 36, lifetime: false, install: true, qual: INSTALL_INCLUDED },
  { kind: 'bathtub_massage_jet', part: 'Water Pump', months: 60, lifetime: false, install: true, qual: INSTALL_INCLUDED },
  { kind: 'kitchen_sink_ss304', part: 'Rust Resistant', months: 300, lifetime: false, install: false, defects: ['dft-rust'], qual: `Anti-Rust against body finishing affected by rust due to manufacturing defect and subject to the fulfilment of the terms stipulated in Sorento's manual/user guide (if any). ${INSTALL_EXCLUDED}` },
  ceramicBody('ceramic_kitchen_sink'),
  { kind: 'kitchen_bathroom_tap_ss304', part: 'Rust Resistant', months: 120, lifetime: false, install: false, defects: ['dft-rust'], qual: `Rust Resistant against body finishing affected by rust due to manufacturing defect and subject to the fulfilment of the terms stipulated in Sorento's manual/user guide (if any). ${INSTALL_EXCLUDED}` },
  { kind: 'kitchen_mixer_cold_tap', part: 'Pull out Flexible Hose & Flexible Hose', months: 24, lifetime: false, install: false, qual: INSTALL_EXCLUDED },
  { kind: 'kitchen_mixer_tap', part: 'Inlet Flexible Hose', months: 60, lifetime: false, install: false, qual: INSTALL_EXCLUDED },
  { kind: 'booster_pump', part: 'Manufacturing Defects', months: 24, lifetime: false, install: false, bonus: 12, qual: `3 years from date of purchase (2 + 1 year extended warranty with online registration). ${INSTALL_EXCLUDED}` },
  { kind: 'booster_pump', part: 'PC Auto Controller', months: 12, lifetime: false, install: false, qual: INSTALL_EXCLUDED },
  { kind: 'hand_shower', part: 'PVC Flexible Hose', months: 60, lifetime: false, install: false, qual: INSTALL_EXCLUDED },
  { kind: 'hand_bidet', part: 'PVC Flexible Hose', months: 60, lifetime: false, install: false, qual: INSTALL_EXCLUDED },
  { kind: 'flush_valves_concealed_cistern', part: 'Piston and Lever Mechanism', months: 12, lifetime: false, install: false, qual: INSTALL_EXCLUDED },
  { kind: 'sensor_tap', part: 'Sensor Eye and Solenoid Valve', months: 12, lifetime: false, install: false, qual: 'Applies to Sensor Taps, Sensor Soap Dispenser, Sensor Hand Dryer and Sensor Flush Valves. Installation is excluded.' },
  { kind: 'self_closing_tap', part: 'Soft Close Mechanism', months: 12, lifetime: false, install: false, qual: INSTALL_EXCLUDED },
];

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

let terms: WarrantyTermRow[] = TERM_SEED.map((t) => {
  const kind = kinds.find((k) => k.code === t.kind)!;
  return {
    id: `term-${t.kind}-${slug(t.part)}`,
    policy_id: 'pol-v15',
    kind_id: kind.id,
    kind_code: kind.code,
    kind_name: kind.name,
    part_name: t.part,
    duration_months: t.months,
    is_lifetime: t.lifetime,
    covered_defect_type_ids: t.defects ?? null,
    covered_defect_type_labels: labelsFor(t.defects ?? null),
    installation_included: t.install,
    registration_bonus_months: t.bonus ?? null,
    qualifications: t.qual ?? null,
    exclusions: t.excl ?? null,
    assessment_count: t.assessments ?? 0,
  };
});

function labelsFor(ids: string[] | null): string[] | null {
  if (!ids) return null;
  return ids.map((id) => DEFECT_TYPES.find((d) => d.id === id)?.label ?? id);
}

// ── The two Kind Rules ──────────────────────────────────────────────────────

let kindRules: WarrantyKindRuleRow[] = [
  {
    id: 'rule-honeycomb',
    kind_id: kindId('bathroom_furniture'),
    kind_code: 'bathroom_furniture',
    kind_name: 'Bathroom Furniture',
    match_type: 'series',
    match_value: 'Honeycomb',
    priority: 0,
  },
  {
    id: 'rule-mirror-cabinet-list',
    kind_id: kindId('mirror_cabinet'),
    kind_code: 'mirror_cabinet',
    kind_name: 'Mirror Cabinet',
    match_type: 'model_list',
    match_value:
      'SRTMCB8071-BL, SRTMCB6071-BL, SRTMCB6070-BL, SRTMCB5060-BL, SRTMCB5061-BL, SRTMCB6066-BL, SRTMCB4561-BL, SRTMCB4560-BL',
    priority: 0,
  },
];

// ── Derived counters ────────────────────────────────────────────────────────

function recount(): void {
  kinds = kinds.map((k) => {
    const rule_count = kindRules.filter((r) => r.kind_id === k.id).length;
    const term_count = terms.filter((t) => t.kind_id === k.id).length;
    // AC-P17: the flags are produced HERE (the server's stand-in), never in a cell.
    return { ...k, rule_count, term_count, has_no_rules: rule_count === 0, has_no_terms: term_count === 0 };
  });
  policies = policies.map((p) => ({
    ...p,
    term_count: terms.filter((t) => t.policy_id === p.id).length,
  }));
}

recount();

let nextId = 1;
const newId = (prefix: string) => `${prefix}-new-${nextId++}`;

// ── Policies ────────────────────────────────────────────────────────────────

/** AC-P2b arithmetic, verbatim: both ends inclusive, NULL `effective_to` = open ended. */
function overlapping(
  candidateFrom: string,
  candidateTo: string | null,
  excludeId: string | null,
): WarrantyPolicyRow | null {
  const INF = '9999-12-31';
  const aFrom = candidateFrom;
  const aTo = candidateTo ?? INF;
  return (
    policies.find((p) => {
      if (p.id === excludeId) return false;
      const bTo = p.effective_to ?? INF;
      return aFrom <= bTo && p.effective_from <= aTo;
    }) ?? null
  );
}

function overlapMessage(other: WarrantyPolicyRow): string {
  const range = other.effective_to
    ? `${other.effective_from} to ${other.effective_to}`
    : `${other.effective_from} onwards`;
  return `Effective range overlaps policy ${other.version} (${range}). Supersede ${other.version} instead, or change the dates.`;
}

export function mockListPolicies(query: string): WarrantyPolicyRow[] {
  if (isEmptyScenario()) return [];
  const q = query.trim().toLowerCase();
  const rows = q ? policies.filter((p) => p.version.toLowerCase().includes(q)) : policies;
  return [...rows].sort((a, b) => (a.effective_from < b.effective_from ? 1 : -1));
}

export function mockGetPolicy(id: string): WarrantyPolicyRow {
  const row = policies.find((p) => p.id === id);
  if (!row) throw new Error('Policy not found.');
  return row;
}

export function mockCreatePolicy(body: WarrantyPolicyWrite): WarrantyPolicyRow {
  if (policies.some((p) => p.version.toLowerCase() === body.version.trim().toLowerCase())) {
    throw new Error(`Version ${body.version} already exists for this company.`);
  }
  const clash = overlapping(body.effective_from, body.effective_to, null);
  if (clash) throw new Error(overlapMessage(clash));
  const row: WarrantyPolicyRow = {
    id: newId('pol'),
    version: body.version.trim(),
    effective_from: body.effective_from,
    effective_to: body.effective_to,
    policy_text: body.policy_text,
    source_attachment_name: null,
    term_count: 0,
    created_at: '2026-08-09T10:00:00',
    updated_at: null,
  };
  policies = [...policies, row];
  recount();
  return mockGetPolicy(row.id);
}

export function mockUpdatePolicy(id: string, body: WarrantyPolicyWrite): WarrantyPolicyRow {
  const clash = overlapping(body.effective_from, body.effective_to, id);
  if (clash) throw new Error(overlapMessage(clash));
  policies = policies.map((p) =>
    p.id === id
      ? {
          ...p,
          version: body.version.trim(),
          effective_from: body.effective_from,
          effective_to: body.effective_to,
          policy_text: body.policy_text,
          updated_at: '2026-08-09T10:05:00',
        }
      : p,
  );
  return mockGetPolicy(id);
}

export function mockDeletePolicy(id: string): void {
  policies = policies.filter((p) => p.id !== id);
  terms = terms.filter((t) => t.policy_id !== id);
  recount();
}

/** One transaction: close the incumbent the day before, create the successor (AC-P2a). */
export function mockSupersedePolicy(id: string, body: WarrantyPolicyWrite): SupersedeResult {
  const incumbent = policies.find((p) => p.id === id);
  if (!incumbent) throw new Error('Policy not found.');
  if (body.effective_from <= incumbent.effective_from) {
    throw new Error(
      `The successor must start after ${incumbent.version} did (${incumbent.effective_from}).`,
    );
  }
  if (policies.some((p) => p.version.toLowerCase() === body.version.trim().toLowerCase())) {
    throw new Error(`Version ${body.version} already exists for this company.`);
  }
  const dayBefore = addDays(body.effective_from, -1);
  policies = policies.map((p) =>
    p.id === id ? { ...p, effective_to: dayBefore, updated_at: '2026-08-09T10:10:00' } : p,
  );
  const created: WarrantyPolicyRow = {
    id: newId('pol'),
    version: body.version.trim(),
    effective_from: body.effective_from,
    effective_to: body.effective_to,
    policy_text: body.policy_text,
    source_attachment_name: null,
    term_count: 0,
    created_at: '2026-08-09T10:10:00',
    updated_at: null,
  };
  policies = [...policies, created];
  recount();
  return { closed: mockGetPolicy(id), created: mockGetPolicy(created.id) };
}

function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + days);
  return dt.toISOString().slice(0, 10);
}

// ── Terms ───────────────────────────────────────────────────────────────────

export function mockListTermsGrouped(policyId: string): WarrantyTermsGrouped {
  if (isEmptyScenario()) return { groups: [], total: 0 };
  const mine = terms.filter((t) => t.policy_id === policyId);
  const byKind = new Map<string, WarrantyTermRow[]>();
  mine.forEach((t) => {
    byKind.set(t.kind_id, [...(byKind.get(t.kind_id) ?? []), t]);
  });
  const groups = kinds
    .filter((k) => byKind.has(k.id))
    .map((k) => ({
      kind: { id: k.id, code: k.code, name: k.name } as WarrantyKindRef,
      terms: [...(byKind.get(k.id) ?? [])].sort((a, b) =>
        a.part_name.localeCompare(b.part_name),
      ),
    }));
  return { groups, total: mine.length };
}

function assertDurationXorLifetime(body: WarrantyTermWrite): void {
  const hasMonths = body.duration_months != null && body.duration_months > 0;
  if (hasMonths === body.is_lifetime) {
    throw new Error('A term needs either a duration in months or lifetime cover, never both.');
  }
}

export function mockCreateTerm(policyId: string, body: WarrantyTermWrite): WarrantyTermRow {
  assertDurationXorLifetime(body);
  const kind = kinds.find((k) => k.id === body.kind_id);
  if (!kind) throw new Error('Unknown product kind.');
  if (
    terms.some(
      (t) =>
        t.policy_id === policyId &&
        t.kind_id === body.kind_id &&
        t.part_name.toLowerCase() === body.part_name.trim().toLowerCase(),
    )
  ) {
    throw new Error(`${kind.name} already has a term for ${body.part_name} under this policy.`);
  }
  const row: WarrantyTermRow = {
    id: newId('term'),
    policy_id: policyId,
    kind_id: kind.id,
    kind_code: kind.code,
    kind_name: kind.name,
    part_name: body.part_name.trim(),
    duration_months: body.is_lifetime ? null : body.duration_months,
    is_lifetime: body.is_lifetime,
    covered_defect_type_ids: body.covered_defect_type_ids,
    covered_defect_type_labels: labelsFor(body.covered_defect_type_ids),
    installation_included: body.installation_included,
    registration_bonus_months: body.registration_bonus_months,
    qualifications: body.qualifications,
    exclusions: body.exclusions,
    assessment_count: 0,
  };
  terms = [...terms, row];
  recount();
  return row;
}

export function mockUpdateTerm(
  policyId: string,
  termId: string,
  body: WarrantyTermWrite,
): WarrantyTermRow {
  assertDurationXorLifetime(body);
  const kind = kinds.find((k) => k.id === body.kind_id);
  if (!kind) throw new Error('Unknown product kind.');
  // Scoped by policy as well as id: a Term is only ever reachable through its
  // Policy (AC-P9), and the mock keeps that shape so the swap is a no-op.
  terms = terms.map((t) =>
    t.id === termId && t.policy_id === policyId
      ? {
          ...t,
          kind_id: kind.id,
          kind_code: kind.code,
          kind_name: kind.name,
          part_name: body.part_name.trim(),
          duration_months: body.is_lifetime ? null : body.duration_months,
          is_lifetime: body.is_lifetime,
          covered_defect_type_ids: body.covered_defect_type_ids,
          covered_defect_type_labels: labelsFor(body.covered_defect_type_ids),
          installation_included: body.installation_included,
          registration_bonus_months: body.registration_bonus_months,
          qualifications: body.qualifications,
          exclusions: body.exclusions,
        }
      : t,
  );
  recount();
  const row = terms.find((t) => t.id === termId);
  if (!row) throw new Error('Term not found.');
  return row;
}

export function mockDeleteTerm(policyId: string, termId: string): void {
  terms = terms.filter((t) => !(t.id === termId && t.policy_id === policyId));
  recount();
}

// ── Kinds ───────────────────────────────────────────────────────────────────

export function mockListKinds(query: string): WarrantyKindRow[] {
  if (isEmptyScenario()) return [];
  const q = query.trim().toLowerCase();
  const rows = q
    ? kinds.filter(
        (k) =>
          k.name.toLowerCase().includes(q) ||
          k.code.toLowerCase().includes(q) ||
          (k.consumer_label ?? '').toLowerCase().includes(q),
      )
    : kinds;
  return [...rows].sort((a, b) => a.sort_order - b.sort_order);
}

export function mockListKindOptions(): WarrantyKindRef[] {
  return [...kinds]
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((k) => ({ id: k.id, code: k.code, name: k.name }));
}

export function mockCreateKind(body: WarrantyKindWrite): WarrantyKindRow {
  if (kinds.some((k) => k.code.toLowerCase() === body.code.trim().toLowerCase())) {
    throw new Error(`Code ${body.code} is already used by another kind.`);
  }
  const row: WarrantyKindRow = {
    id: newId('kind'),
    code: body.code.trim(),
    name: body.name.trim(),
    consumer_label: body.consumer_label,
    consumer_icon: body.consumer_icon,
    sort_order: body.sort_order,
    is_active: body.is_active,
    rule_count: 0,
    term_count: 0,
    has_no_rules: true,
    has_no_terms: true,
  };
  kinds = [...kinds, row];
  recount();
  return row;
}

export function mockUpdateKind(id: string, body: WarrantyKindWrite): WarrantyKindRow {
  kinds = kinds.map((k) =>
    k.id === id
      ? {
          ...k,
          code: body.code.trim(),
          name: body.name.trim(),
          consumer_label: body.consumer_label,
          consumer_icon: body.consumer_icon,
          sort_order: body.sort_order,
          is_active: body.is_active,
        }
      : k,
  );
  // A rename has to reach the rows that quote the name, or the Rules grid and the
  // Terms groups keep printing the old one until a reload.
  kindRules = kindRules.map((r) =>
    r.kind_id === id ? { ...r, kind_code: body.code.trim(), kind_name: body.name.trim() } : r,
  );
  terms = terms.map((t) =>
    t.kind_id === id ? { ...t, kind_code: body.code.trim(), kind_name: body.name.trim() } : t,
  );
  recount();
  const row = kinds.find((k) => k.id === id);
  if (!row) throw new Error('Kind not found.');
  return row;
}

/** AC-P12: refused while referenced, and the refusal names BOTH counts. */
export function mockDeleteKind(id: string): void {
  const kind = kinds.find((k) => k.id === id);
  if (!kind) throw new Error('Kind not found.');
  const termCount = terms.filter((t) => t.kind_id === id).length;
  const ruleCount = kindRules.filter((r) => r.kind_id === id).length;
  if (termCount > 0 || ruleCount > 0) {
    throw new Error(
      `${kind.name} is still referenced by ${termCount} term${termCount === 1 ? '' : 's'} and ` +
        `${ruleCount} rule${ruleCount === 1 ? '' : 's'}. Remove those first.`,
    );
  }
  kinds = kinds.filter((k) => k.id !== id);
  recount();
}

// ── Kind rules ──────────────────────────────────────────────────────────────

export function mockListKindRules(kindIdFilter: string | null): WarrantyKindRuleRow[] {
  if (isEmptyScenario()) return [];
  const rows = kindIdFilter ? kindRules.filter((r) => r.kind_id === kindIdFilter) : kindRules;
  return [...rows].sort(
    (a, b) => b.priority - a.priority || a.kind_name.localeCompare(b.kind_name),
  );
}

function decorateRule(body: WarrantyKindRuleWrite, id: string): WarrantyKindRuleRow {
  const kind = kinds.find((k) => k.id === body.kind_id);
  if (!kind) throw new Error('Unknown product kind.');
  if (!body.match_value.trim()) {
    throw new Error('A rule with an empty value matches nothing. Give it a value.');
  }
  return {
    id,
    kind_id: kind.id,
    kind_code: kind.code,
    kind_name: kind.name,
    match_type: body.match_type,
    match_value: body.match_value.trim(),
    priority: body.priority,
  };
}

export function mockCreateKindRule(body: WarrantyKindRuleWrite): WarrantyKindRuleRow {
  const row = decorateRule(body, newId('rule'));
  kindRules = [...kindRules, row];
  recount();
  return row;
}

export function mockUpdateKindRule(id: string, body: WarrantyKindRuleWrite): WarrantyKindRuleRow {
  const row = decorateRule(body, id);
  kindRules = kindRules.map((r) => (r.id === id ? row : r));
  recount();
  return row;
}

export function mockDeleteKindRule(id: string): void {
  kindRules = kindRules.filter((r) => r.id !== id);
  recount();
}

// ── The tester - mirrors the production ranking (see header) ────────────────

const SPECIFICITY: KindRuleMatchType[] = ['model_list', 'model_prefix', 'series', 'category'];

function matchedLength(
  rule: { match_type: KindRuleMatchType; match_value: string },
  productCode: string,
  categoryCode: string,
  productName: string,
): number | null {
  const value = rule.match_value.trim();
  if (!value) return null; // an empty value matches NOTHING, never everything
  if (rule.match_type === 'category') {
    return categoryCode && value.toLowerCase() === categoryCode ? value.length : null;
  }
  if (rule.match_type === 'model_prefix') {
    return productCode && productCode.startsWith(value.toLowerCase()) ? value.length : null;
  }
  if (rule.match_type === 'model_list') {
    for (const raw of value.split(',')) {
      const token = raw.trim();
      if (token && productCode && token.toLowerCase() === productCode) return token.length;
    }
    return null;
  }
  if (rule.match_type === 'series') {
    return productName && productName.includes(value.toLowerCase()) ? value.length : null;
  }
  return null;
}

export function mockTestKindRules(body: KindRuleTestRequest): KindRuleTestResponse {
  const code = (body.product_code ?? '').trim().toLowerCase();
  const category = (body.category_code ?? '').trim().toLowerCase();
  const name = (body.product_name ?? '').trim().toLowerCase();
  if (!code && !category && !name) {
    return { resolved_kind: null, deciding_rule: null, matches: [] };
  }

  const candidates: TestedRule[] = kindRules.map((r) => ({
    id: r.id,
    kind_id: r.kind_id,
    match_type: r.match_type,
    match_value: r.match_value,
    priority: r.priority,
    is_candidate: false,
  }));
  if (body.candidate_rule) {
    candidates.push({
      id: null,
      kind_id: body.candidate_rule.kind_id,
      match_type: body.candidate_rule.match_type,
      match_value: body.candidate_rule.match_value,
      priority: body.candidate_rule.priority,
      is_candidate: true,
    });
  }

  const scored = candidates
    .map((rule) => {
      const kind = kinds.find((k) => k.id === rule.kind_id);
      if (!kind || !kind.is_active) return null;
      const len = matchedLength(rule, code, category, name);
      if (len === null) return null;
      return { rule, kind, len };
    })
    .filter((x): x is { rule: TestedRule; kind: WarrantyKindRow; len: number } => x !== null);

  scored.sort((a, b) => {
    const pa = -a.rule.priority;
    const pb = -b.rule.priority;
    if (pa !== pb) return pa - pb;
    const sa = SPECIFICITY.indexOf(a.rule.match_type);
    const sb = SPECIFICITY.indexOf(b.rule.match_type);
    if (sa !== sb) return sa - sb;
    if (a.len !== b.len) return b.len - a.len;
    return a.kind.code.localeCompare(b.kind.code);
  });

  const matches: KindRuleTestMatch[] = scored.map((s, i) => ({
    rank: i + 1,
    rule: s.rule,
    kind: { id: s.kind.id, code: s.kind.code, name: s.kind.name },
    matched_length: s.len,
    is_candidate: s.rule.is_candidate,
  }));

  return {
    resolved_kind: matches[0]?.kind ?? null,
    deciding_rule: matches[0]?.rule ?? null,
    matches,
  };
}

// ── Defect types ────────────────────────────────────────────────────────────

export function mockListDefectTypes(): DefectTypeOption[] {
  return DEFECT_TYPES;
}

export { settle as mockSettle };
