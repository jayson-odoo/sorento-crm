'use client';

/**
 * Manage fonts: the "Brand fonts" dialog (`FontUploadDialog`) on the ONE kit library, the single
 * wiring both designers use (the template designer and the spec sheet, v3 review S2). An upload is
 * selectable at once in both (the library cache is shared); a rename hands the old and new family
 * names back so the open document(s) can follow it; a delete started here keeps counting down after
 * the dialog closes, so closing catches the library up.
 */

import { FontUploadDialog } from './FontUploadDialog';
import { useKitLibrary } from './useTagBindings';

export function ManageFontsDialog({
  open,
  onClose,
  onFamilyRenamed,
}: {
  open: boolean;
  onClose: () => void;
  /** A brand font was renamed: rewrite the layers that name `oldName`. */
  onFamilyRenamed?: (oldName: string, newName: string) => void;
}) {
  const library = useKitLibrary();
  return (
    <FontUploadDialog
      open={open}
      fonts={library.fonts}
      onCancel={() => {
        onClose();
        // A delete started inside the dialog keeps counting down after it closes (D7: the window
        // is the server's, not the dialog's), so catch up on whatever happened while it was open,
        // or the Font Family list can go on offering a family the server already deleted.
        void library.reload();
      }}
      onUploaded={(asset) => {
        library.remember(asset);
        onClose();
      }}
      onRenamed={(asset, oldName) => {
        library.rename(asset.id, asset.name);
        onFamilyRenamed?.(oldName, asset.name);
        void library.reload();
      }}
      onDeleted={(id) => {
        library.forget(id);
        void library.reload();
      }}
    />
  );
}
