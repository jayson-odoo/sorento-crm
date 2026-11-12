# UAC - COMBO-RENAME

- AC-1: A user with `master_data.products.edit` sees a pencil (labelled "Rename combo <name>") next to each combo
  title on product detail > Combos. A user without it sees no pencil.
- AC-2: The pencil swaps the title for a text input holding the current name, with Save and Cancel. Enter saves,
  Escape cancels. Cancel / Escape restore the title with no write.
- AC-3: Save sends the trimmed name; on success the title shows the new name. Saving the unchanged name closes the
  editor with no write.
- AC-4: An empty (or whitespace) name shows "A combo needs a name" under the input and sends nothing.
- AC-5: A name another combo on the same product already has (any letter case) shows "Another combo on this product
  already has this name" under the input; the editor stays open.
- AC-6: The rename input and the Add combo modal name input both cap at 100 characters; the API answers 422 for a
  101-character name on create and on update.
- AC-7: Price tags show the new name with no other change (they read the combo by id).
