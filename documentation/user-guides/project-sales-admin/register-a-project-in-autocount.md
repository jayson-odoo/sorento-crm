# Register a project in AutoCount

Use this to create the project in AutoCount from its CRM record, so AutoCount documents can be
filed under the same project number.

## Before you start

* An administrator turns on **AutoCount project registration** in **Settings**. It is off until
  the AutoCount connection for projects is ready; while it is off the project page shows nothing
  new.
* You need the permission to send Project sales records to AutoCount.
* Only an approved project that is not marked lost can be registered.

## Steps

1. Open **Project Sales** and open the project.
2. Open the gear menu in the page header and choose **Register in AutoCount**.
   * If the item is greyed out, it shows why, for example **Waiting for AutoCount** (AutoCount is
     not ready to take projects yet) or **Could not reach AutoCount**.
3. A window shows AutoCount's answer:
   * **Registered**: the AutoCount project number now shows beside the project's status in the
     header, and the menu item goes away.
   * **Refused**: the reason AutoCount gave. Fix the cause, then choose **Register in AutoCount**
     again.
   * **Sent; AutoCount has not confirmed yet**: choose **Register in AutoCount** again later. The
     same request is sent again, so the project is never created twice in AutoCount.

## What's captured

* The project is sent with its project number, its title, and its location (or address).
* The AutoCount project number and the date it was registered are kept on the project.
* Every attempt is recorded with the person who pressed it, and shows on the project's
  **Activity** tab ("Registered in AutoCount as ..." or "AutoCount registration not completed:
  ...").
* Registering happens once. Later changes to the project's title or site are not sent to
  AutoCount.
