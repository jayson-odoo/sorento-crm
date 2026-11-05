# UAC: Projects board view pref

- AC-1 Board card code and title do not underline on hover; they take the grid link's hover colour. Card stays clickable, full-title tooltip stays.
- AC-2 Picking Grid on Pipeline and reloading (or navigating away and back) opens Grid.
- AC-3 The choice is stored per user on the server (`user_list_column_configs`, key `projects.projects.view::pipeline`, `view`), so another user's view is unaffected and the choice follows the user to another browser.
- AC-4 A user who never picked still lands on Board.
- AC-5 Saving the view does not erase that user's stored columns, sort or page size (partial merge).
