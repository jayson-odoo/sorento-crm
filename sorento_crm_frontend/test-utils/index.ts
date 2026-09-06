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
  await screen.findByLabelText(label);
  await waitFor(() =>
    expect(
      Array.from(
        (screen.getByLabelText(label) as HTMLSelectElement).options,
      ).map((o) => o.value),
    ).toContain(value),
  );
  // Re-queried, never the handle the wait above started with: see the note on
  // `tickCheckbox` for why a held handle is not safe to fire an event at.
  const select = screen.getByLabelText(label) as HTMLSelectElement;
  fireEvent.change(select, { target: { value } });
  expect(select.value).toBe(value);
  return select;
}

/** Is this control ticked, whether it is a native input or an ARIA checkbox? */
function isTicked(element: HTMLElement): boolean {
  return element instanceof HTMLInputElement
    ? element.checked
    : element.getAttribute('aria-checked') === 'true';
}

/**
 * Tick the checkbox labelled `label` and confirm the tick took.
 *
 * Two silent no-ops live here, and a DataGrid selection meets both.
 *
 * The first is a stale handle: `const box = await screen.findByLabelText(...)`
 * followed by `fireEvent.click(box)` fires at the node the query returned, and
 * an `await` in between hands the machine back to React - a commit that lands
 * in that gap (a fetch resolving, a provider mounting) can replace that node,
 * and a click on a node no longer in the tree does nothing at all. So the
 * click here is always fired at the CURRENT node.
 *
 * The second is the assertion's distance from the click. `TagTemplatesList`
 * clicked "Select all rows on this page" and then waited for the bulk strip's
 * Delete button, which exists only if the click selected something: when it
 * did not, CI reported a missing Delete button (twice, once after the wait had
 * been widened to 8s in the belief it was slowness), and the DOM it dumped had
 * no selection in it at all. Waiting for `aria-checked` puts the failure on
 * the control that was clicked.
 */
export async function tickCheckbox(
  label: string | RegExp,
): Promise<HTMLElement> {
  await screen.findByLabelText(label);
  fireEvent.click(screen.getByLabelText(label));
  await waitFor(() => expect(isTicked(screen.getByLabelText(label))).toBe(true));
  return screen.getByLabelText(label);
}
