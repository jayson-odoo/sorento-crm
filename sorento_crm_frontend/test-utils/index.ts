/**
 * Shared jsdom waits for component specs.
 *
 * Both helpers exist because of the same defect class, which cost two prod
 * deploys on 5-6 Sep 2026: a spec waited on something that was ALREADY true,
 * so the wait returned on the first tick and the assertions ran against a
 * half-loaded component. That passes on an idle machine, where the mocked
 * promise happens to have settled anyway, and fails on a loaded CI runner,
 * where it has not - so the failure reads as a code regression and is not one.
 *
 * The rule these encode: wait for the DOM to CHANGE, and fail loudly when the
 * thing you meant to wait for was never there. A wait that cannot fail is not
 * a wait.
 */
import { expect } from 'vitest';
import {
  fireEvent,
  screen,
  waitFor,
  waitForElementToBeRemoved,
} from '@testing-library/react';

/** What `components/common/SectionSkeleton` puts on its wrapper. */
const SECTION_SKELETON = '[data-slot="section-skeleton"]';

/**
 * Wait out the `SectionSkeleton` a component renders while its own data is in
 * flight, and return once the real content is on screen.
 *
 * Use this instead of a text matcher. The portal specs used to wait for
 * `queryByText(/^loading/i)` to be null, which stopped meaning anything the
 * day the spinner-and-the-word-Loading became a skeleton (M5-02): the text was
 * never in the DOM, so the wait resolved immediately and the next
 * `getByText` ran against six grey bars.
 *
 * `waitForElementToBeRemoved` throws when the skeleton is not on screen at the
 * moment of the call, which is the property that makes this safe to copy: a
 * wait that guards nothing reports itself instead of going quiet.
 */
export async function waitForSectionLoaded(): Promise<void> {
  await waitForElementToBeRemoved(() =>
    Array.from(document.querySelectorAll(SECTION_SKELETON)),
  );
}

/**
 * Pick `value` on the `<select>` labelled `label`, once that option exists.
 *
 * `fireEvent.change` on a `<select>` that has no matching `<option>` is a
 * silent no-op: jsdom leaves the value at '', React is handed '', and the
 * field stays empty. Every option that arrives from a lookup (the portal's
 * Debtor list, say) is absent for the first render, so a spec that fires the
 * change straight after `findByLabelText` is racing the lookup promise - it
 * wins on an idle machine and loses under CI load, where the form then refuses
 * to submit and the failure names the submit mock rather than the field.
 *
 * Both halves are guards: the wait is for the option to exist, and the
 * assertion afterwards is for the value to have actually taken, so a select
 * that ignores the change fails here, on the line that set it.
 */
export async function selectOption(
  label: string | RegExp,
  value: string,
): Promise<HTMLSelectElement> {
  const select = (await screen.findByLabelText(label)) as HTMLSelectElement;
  await waitFor(() =>
    expect(Array.from(select.options).map((o) => o.value)).toContain(value),
  );
  fireEvent.change(select, { target: { value } });
  expect(select.value).toBe(value);
  return select;
}
