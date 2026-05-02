# Purchasing — Manage folders, files, and Quick Access

Folders help organise attachments (packing lists, product attachments, etc.) so they're easier to find. Folder operations live on a dedicated page, separate from the attachment list.

## Where to manage folders

Open **Resource Management → Attachment Directories** (URL: `/resource-management/attachment-directories`). The page shows the folder tree on the left.

## Folder operations

Click the `⋯` menu on any folder row to see the available actions:

| Action | Menu item |
|---|---|
| Create a child folder | **Add subfolder** |
| Rename a folder | **Rename** |
| Delete a folder | **Delete** |
| Adjust who can see this folder | **Adjust access levels** |
| Pin folder to Quick Access | **Pin to Quick Access** |
| Remove from Quick Access | **Unpin from Quick Access** |

To **create a top-level folder**, use the create control at the root of the directory tree.

## Rename a file

File renaming is done from the attachments list, not the directory tree:

1. Open **Resource Management → Attachments**.
2. Find the file row.
3. Click the **pencil** icon in the actions column.
4. Edit the name in the **Rename file** dialog and confirm.

## Quick Access

Quick Access is the pinned-shortcuts section in the left sidebar. Use it for menu items and folders you visit often.

- **Pin a menu item:** in the sidebar, expand **Quick Access** → click **+ Add shortcut** → search for the menu item → confirm.
- **Pin a folder:** open the folder's `⋯` menu → **Pin to Quick Access**.
- **Reorder shortcuts:** drag-and-drop within the Quick Access list.
- **Unpin:** click the unpin (PinOff) icon next to the shortcut, or use **Unpin from Quick Access** on the folder's `⋯` menu.

> Quick Access is gated by the `menu.quick_access.pin` and `menu.quick_access.unpin` permissions. If you don't see the section, ask your admin to grant them.

## See also

- [Shared upload flow](../_shared/upload-flow.md)
