/**
 * PRICETAG-COMBO-RENDER K4 (FE half): what a template needs from a combo and whether the
 * combo fits. Pure. The words match the backend's `template_needs.fit_reason` exactly.
 */
import type { ComboPartOption } from '@/app/(auth)/portal/lib/price-tag-request-service';
import type { SubjectSlot, TagSlots } from './tag-template-types';

/** What a template reads: highest position per kind (from its published layers). */
export interface TemplateNeeds {
  fixed: number;
  groups: number[];
  upgrades: number;
}

/** What a combo offers: fixed parts, choice groups in first-appearance order, upgrades. */
export interface ComboShape {
  fixed: number;
  groups: { role: string; size: number }[];
  upgrades: number;
}

type ShapePart = Pick<ComboPartOption, 'choice_group' | 'is_upgrade'>;

/** The groups that ARE a choice: 2+ non-upgrade parts. A one-part group is a fixed part (the
 *  backend's `template_needs.pick_one_groups`, COMBO-SETTINGS-UX owner round 1). */
export function pickOneGroups(parts: ShapePart[]): Set<string> {
  const sizes = new Map<string, number>();
  for (const part of parts) {
    if (!part.is_upgrade && part.choice_group) sizes.set(part.choice_group, (sizes.get(part.choice_group) ?? 0) + 1);
  }
  return new Set([...sizes].filter(([, size]) => size > 1).map(([role]) => role));
}

export function comboShape(parts: ShapePart[]): ComboShape {
  const shape: ComboShape = { fixed: 0, groups: [], upgrades: 0 };
  const choices = pickOneGroups(parts);
  for (const part of parts) {
    if (part.is_upgrade) {
      shape.upgrades += 1;
    } else if (part.choice_group && choices.has(part.choice_group)) {
      const group = shape.groups.find((g) => g.role === part.choice_group);
      if (group) group.size += 1;
      else shape.groups.push({ role: part.choice_group, size: 1 });
    } else {
      shape.fixed += 1;
    }
  }
  return shape;
}

const plural = (count: number, noun: string) => (count === 1 ? `${count} ${noun}` : `${count} ${noun}s`);

export function fitReason(needs: TemplateNeeds, shape: ComboShape): string | null {
  // Choice groups, then fixed parts, then upgrades. A group and the upgrades are at most what the
  // combo has; fixed parts are always in the box, so a template must print every one.
  // A plain template (no position read) prints the combo as one product and fits every combo.
  if (!needs.fixed && !needs.upgrades && !needs.groups.some((n) => n > 0)) return null;
  for (let index = 0; index < needs.groups.length; index += 1) {
    const need = needs.groups[index];
    if (need <= 0) continue;
    const group = shape.groups[index];
    if (!group) {
      return shape.groups.length === 0
        ? 'Needs a choice group; this combo has none'
        : `Needs choice group ${index + 1}; this combo has ${shape.groups.length}`;
    }
    if (need > group.size) return `Needs ${need} from ${group.role}; this combo has ${group.size}`;
  }
  if (needs.fixed < shape.fixed) {
    return `Prints ${needs.fixed} of this combo's ${plural(shape.fixed, 'fixed part')}`;
  }
  if (needs.fixed > shape.fixed) {
    return `Needs ${plural(needs.fixed, 'fixed part')}; this combo has ${shape.fixed}`;
  }
  if (needs.upgrades > shape.upgrades) {
    return `Needs ${plural(needs.upgrades, 'upgrade')}; this combo has ${shape.upgrades}`;
  }
  return null;
}

/** "Needs 3 from Kitchen tap, upgrade"; nothing read is "Needs the main product only". */
export function needsText(needs: TemplateNeeds, shape: ComboShape | null): string {
  const pieces: string[] = [];
  needs.groups.forEach((need, index) => {
    if (need <= 0) return;
    pieces.push(`${need} from ${shape?.groups[index]?.role ?? `choice group ${index + 1}`}`);
  });
  if (needs.fixed > 0) pieces.push(plural(needs.fixed, 'fixed part'));
  if (needs.upgrades > 0) pieces.push(needs.upgrades === 1 ? 'upgrade' : `${needs.upgrades} upgrades`);
  return pieces.length ? `Needs ${pieces.join(', ')}` : 'Needs the main product only';
}

/** 0-based index of the group named `role`, -1 when the combo has none. */
export function groupIndexOf(role: string, shape: ComboShape): number {
  return shape.groups.findIndex((g) => g.role === role);
}

/** How many positions the generic list offers when no combo is previewed. */
export const SLOT_PICKER_FIXED = 4;
export const SLOT_PICKER_GROUPS = 3;
export const SLOT_PICKER_PICKS = 5;
export const SLOT_PICKER_UPGRADES = 2;

/** A position a layer or a merge field may read, with the product sitting there and its group. */
export interface ComboPosition {
  slot: SubjectSlot;
  code?: string;
  group?: string;
}

/**
 * The positions after the main product: the previewed combo's own, else the generic counts. The
 * Product select and the Insert field dialog both list positions from here.
 */
export function comboPositions(slots: TagSlots | null | undefined): ComboPosition[] {
  const out: ComboPosition[] = [];
  const fixed = slots ? slots.fixed : Array.from({ length: SLOT_PICKER_FIXED }, () => null);
  fixed.forEach((part, index) => out.push({ slot: { kind: 'fixed', index }, code: part?.code }));
  const groups = slots
    ? slots.groups.map((g) => ({ role: g.role, picks: g.picks }))
    : Array.from({ length: SLOT_PICKER_GROUPS }, (_, g) => ({
        role: `Choice group ${g + 1}`,
        picks: Array.from({ length: SLOT_PICKER_PICKS }, () => null),
      }));
  groups.forEach((group, g) =>
    group.picks.forEach((part, index) =>
      out.push({ slot: { kind: 'pick', group: g, index }, code: part?.code, group: group.role }),
    ),
  );
  const upgrades = slots ? slots.upgrades : Array.from({ length: SLOT_PICKER_UPGRADES }, () => null);
  upgrades.forEach((part, index) => out.push({ slot: { kind: 'upgrade', index }, code: part?.code }));
  return out;
}
