/**
 * FILES-MOVE-DUPLICATE crew pass: the details window names a file by its visible name and,
 * when it differs, shows the name it was first uploaded under beside it.
 */
import { describe, it, expect } from 'vitest';
import { attachmentDisplayNames } from './attachmentDisplayName';

describe('attachmentDisplayNames', () => {
  it('a never-renamed file: one name, no original line', () => {
    expect(attachmentDisplayNames({ stored_filename: 'invoice.pdf', original_filename: 'invoice.pdf' })).toEqual({
      name: 'invoice.pdf',
      originalName: null,
    });
  });

  it('a renamed file: the visible name, with the original beside it, brackets kept', () => {
    expect(
      attachmentDisplayNames({ stored_filename: 'invoice (1).pdf', original_filename: 'invoice.pdf' })
    ).toEqual({ name: 'invoice (1).pdf', originalName: 'invoice.pdf' });
  });

  it('only a change of letter case is not shown as a second name', () => {
    expect(attachmentDisplayNames({ stored_filename: 'Photo.JPG', original_filename: 'photo.jpg' }).originalName).toBeNull();
  });

  it('no visible name falls back to the original', () => {
    expect(attachmentDisplayNames({ stored_filename: '', original_filename: 'scan.pdf' })).toEqual({
      name: 'scan.pdf',
      originalName: null,
    });
  });
});
