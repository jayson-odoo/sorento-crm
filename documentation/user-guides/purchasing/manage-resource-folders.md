# 1.6-Purchasing - Manage folders, files, and Quick Access

Folders help organise attachments (packing lists, product attachments, promotions, marketing forms, etc.) so they are easier to find. Folder operations live on the same **Files** page as the attachments, on the left **Folders** sidebar.

## Where to manage folders

Open **[Resource Management → Files](/resource-management/attachment-directories)** (URL: `/resource-management/attachment-directories`). The page is titled **Files**. The folder tree is on the left; the attachments table is on the right.

## Folder operations

Click **Folder actions** (the `⋯` button on a folder row) to see the menu:

| Action | Menu item |
|----|----|
| Create a child folder | **Add subfolder** |
| Rename a folder | **Rename** |
| Delete a folder | **Delete** |
| Restrict who can see this folder | **Adjust access levels** |
| Pin folder to Quick Access | **Pin to Quick Access** |
| Remove from Quick Access | **Unpin from Quick Access** |

To **create a top-level folder**, click **[Add](/resource-management/attachment-directories#guide_target=resource-management.files.add-folder-button)** at the top of the **Folders** sidebar (next to the **Expand all** / **Collapse all** buttons). The dialog is titled **New folder** for top-level and **New subfolder** for children.

## Search folders

Type into the **Search folders…** box at the top of the sidebar to filter the tree.

## File actions (right-click menu)

File rows in the attachments table no longer have a pencil / **Actions** column on the right. Instead, **right-click the file row** (or **long-press** on a touch device) to open its action menu. The menu items are:

| Action | Menu item |
|----|----|
| Open the file | **Open** |
| Preview in-app | **Preview** |
| Download | **Download** |
| Rename the file | **Rename** |
| Move to another folder | **Move to…** |
| Re-run the n8n parser on this file | **Resubmit to n8n** |
| Send the file to Trash | **Move to trash** |

(In **Trash**, the menu shows **Restore** and **Permanently delete** instead.)

### Rename a file

1. **Right-click** the file row in the attachments table (right pane) - or long-press on touch.
2. Choose **Rename** from the context menu.
3. Edit the name in the rename dialog and confirm.

### Move files to another folder

1. Tick the files (and folders) to move, then choose **Move to…** from the action menu, or right-click one file and choose **Move to…**. You can also drag files onto a folder in the sidebar.
2. Pick the target folder and confirm.

Every file that can move goes straight away. A folder can hold only one file with a given name, so if the target folder already has a file with the same name, a window opens for that file with three choices:

| Choice | What happens |
|----|----|
| **Rename** | The file moves under the new name shown in the box (for example `photo (1).jpg`). You can type another name. The file itself, its links to products, promotions and forms, and any link already shared stay the same. |
| **Replace** | The file already in the target folder goes to **Trash** and this file takes its place. Records linked to the replaced file stay linked to it; restore it from **Trash** to undo. Only users who may delete files see this choice. |
| **Skip** | The file stays where it is. |

When the move is done, one message sums it up, for example: *2 moved. 1 not moved: photo.jpg already exists in Folder B.*

A file renamed earlier still counts under the name it was first uploaded with. If the target folder holds a file first uploaded under that same name, the message says so, for example: *holiday.jpg cannot be moved into Folder B: photo.jpg there has the same original file name.* Choose **Rename** to move it under a new name.

The same rule applies when you upload a file into a folder: a name already used there (including a file first uploaded under it and renamed since) is refused with a plain message naming the file and the folder.

## Quick Access

Quick Access is the pinned-shortcuts section at the top of the left sidebar. Use it for menu items and folders you visit often.

* **Pin a menu item:** in the sidebar, expand **Quick Access** → click **Add shortcut** → search the menu → confirm.
* **Pin a folder:** open the folder's `⋯` menu → **Pin to Quick Access**.
* **Reorder shortcuts:** drag-and-drop within the Quick Access list.
* **Unpin a shortcut:** click the unpin (PinOff) icon next to the shortcut, or use **Unpin from Quick Access** on the folder's `⋯` menu.

## See also

* [Shared upload flow](../_shared/upload-flow.md)
