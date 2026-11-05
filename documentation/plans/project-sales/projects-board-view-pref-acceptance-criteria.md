# UAC: Projects board view pref

- AC-1 Board card code and title do not underline on hover; the card tints on hover the way a grid row does (`hover:bg-muted/40`). Card stays clickable, full-title tooltip stays.
- AC-2 Picking Grid on Pipeline and reloading (or navigating away and back) opens Grid.
- AC-3 The choice is stored per user on the server (`user_list_column_configs`, key `projects.projects.view::pipeline-view`, `view`; its own row so the grid's Reset columns cannot erase it), so another user's view is unaffected and the choice follows the user to another browser.
- AC-4 A user who never picked still lands on Board.
- AC-5 Saving the view does not erase that user's stored columns, sort or page size (partial merge).
- AC-6 Every Projects grid column sorts on the server, on the value it shows: Stage in stage order, Estimated by amount, Next action by due date with Nothing open last, Flags with Critical first descending; blanks last.
