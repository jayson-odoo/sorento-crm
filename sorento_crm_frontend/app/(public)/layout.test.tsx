import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import PublicCatalogueLayout from './layout';

/**
 * The group has to cancel the app shell, not just decline to add to it.
 *
 * Measured on the running prod build at 1400px before this existed: the
 * catalogue's own `<section className="w-full">` came back 274px wide, two
 * 107px tiles against the left edge of an otherwise blank page. The root layout
 * makes `<body>` a flex ROW so the sidebar can sit beside the content, and a
 * page that supplies no sidebar becomes a lone flex item, which shrinks to fit
 * its contents. `w-full` cannot help: it resolves against a parent that has
 * already collapsed.
 *
 * The `(auth)` group used to hide this. Its `BrandedLayout` wrapped every child
 * in `flex grow w-full` plus a `max-w-6xl` Card, so the catalogue inherited a
 * width along with the sign-in chrome. Leaving that group to stop the PDF being
 * printed inside a sign-in card took the width away with it.
 */
describe('the public catalogue group', () => {
  function css(): string {
    const { container } = render(<PublicCatalogueLayout>{null}</PublicCatalogueLayout>);
    const style = container.querySelector('style');
    return style ? style.innerHTML : '';
  }

  it('takes <body> back out of the shell flex row', () => {
    // `.flex` is a class selector and `body` is an element selector, so the
    // shell's utility wins on specificity. Cancelling it needs !important.
    expect(css()).toMatch(/body[^{]*{[^}]*display:\s*block\s*!important/);
  });

  it('lets the document be as tall as it is, rather than one screen', () => {
    // `h-full` on <body> caps a catalogue at the viewport and hands the
    // overflow to an inner scroller that these routes do not have. On paper it
    // is worse: the printed document would be one page tall.
    expect(css()).toMatch(/body[^{]*{[^}]*height:\s*auto\s*!important/);
  });
});
