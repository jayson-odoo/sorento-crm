/**
 * Crew browser pass (5 Nov): the request preview says which tags lose feature icons. One warning
 * above the sheet, rendered by `DesignViewer` (staff Design, portal live preview, self-approval)
 * and the request designer.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { FeatureIconDropWarning } from './FeatureIconDropWarning';

describe('FeatureIconDropWarning', () => {
  it('lists each tag that loses icons', () => {
    render(
      <FeatureIconDropWarning
        drops={[
          { tagLabel: '2a', dropped: 1 },
          { tagLabel: '3b', dropped: 2 },
        ]}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('Tag 2a: 1 feature icon does not fit its box');
    expect(screen.getByRole('status')).toHaveTextContent('Tag 3b: 2 feature icons do not fit their box');
  });

  it('drops the "Tag" prefix for the template designer\'s one unlabelled tag (7 Nov)', () => {
    render(<FeatureIconDropWarning drops={[]} accessoryDrops={[{ tagLabel: '', dropped: 1 }]} />);
    expect(screen.getByRole('status')).toHaveTextContent(/^1 accessory does not fit its box$/);
  });

  it('labels accessory lines per tag on a request', () => {
    render(<FeatureIconDropWarning drops={[]} accessoryDrops={[{ tagLabel: '1a', dropped: 2 }]} />);
    expect(screen.getByRole('status')).toHaveTextContent('Tag 1a: 2 accessories do not fit their box');
  });

  it('renders nothing when every icon fits', () => {
    const { container } = render(<FeatureIconDropWarning drops={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
