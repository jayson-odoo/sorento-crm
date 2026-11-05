/**
 * PRICETAG-COMBO-RENDER K4 (FE half): what a template needs from a combo and whether the
 * combo fits. Pure. The words match the backend's `template_needs.fit_reason` exactly.
 */
import type { ComboPartOption } from '@/app/(auth)/portal/lib/price-tag-request-service';

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

export function comboShape(parts: ShapePart[]): ComboShape {
  const shape: ComboShape = { fixed: 0, groups: [], upgrades: 0 };
  for (const part of parts) {
    if (part.is_upgrade) {
      shape.upgrades += 1;
    } else if (part.choice_group) {
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
  // Fixed parts are always in the box, so a template must print every one; a choice group and
  // the upgrades are at most what the combo has.
  if (needs.fixed < shape.fixed) {
    return `Prints ${needs.fixed} of this combo's ${plural(shape.fixed, 'fixed part')}`;
  }
  if (needs.fixed > shape.fixed) {
    return `Needs ${plural(needs.fixed, 'fixed part')}; this combo has ${shape.fixed}`;
  }
  for (let index = 0; index < needs.groups.length; index += 1) {
    const need = needs.groups[index];
    if (need <= 0) continue;
    const group = shape.groups[index];
    if (!group) return `Needs choice group ${index + 1}; this combo has ${shape.groups.length}`;
    if (need > group.size) {
      return `Needs ${need} from ${group.role}; this combo has ${group.size}`;
    }
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
