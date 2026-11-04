import { render, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { RichTextEditor } from '@/components/ui/rich-text-editor';

describe('RichTextEditor labelling', () => {
  it('puts id and aria-labelledby on the editable element', async () => {
    const { container } = render(
      <div>
        <span id="lbl">Closing text</span>
        <RichTextEditor value="<p>hi</p>" onChange={() => {}} id="closing-editor" aria-labelledby="lbl" />
      </div>,
    );
    await waitFor(() => expect(container.querySelector('[contenteditable="true"]')).not.toBeNull());
    const editable = container.querySelector('[contenteditable="true"]') as HTMLElement;
    expect(editable.getAttribute('id')).toBe('closing-editor');
    expect(editable.getAttribute('aria-labelledby')).toBe('lbl');
  });
});
