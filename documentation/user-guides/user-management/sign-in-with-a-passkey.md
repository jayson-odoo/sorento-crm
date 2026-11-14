# Sign in with a passkey

A passkey lets you sign in with Face ID, Touch ID or your fingerprint instead of typing a password. Use this guide to add one, sign in with it, and manage it. Admins also use it to turn passkeys on for a person and to remove a person's passkeys.

Passkeys are off by default. You only see the **Passkeys** card once an admin has turned **Passkey sign-in** on for you.

## Sign in with a passkey


1. Open the CRM on the **Sign In** page.
2. Click the round **Passkey** button beside **Phone number**. Your phone or computer then asks for Face ID, Touch ID, your fingerprint or your screen lock.
3. Confirm, and you land where a normal sign-in would take you.

Shortcut: on many browsers, tapping the **Email** field also offers your saved passkey. Pick it and confirm.

If you close the prompt without confirming, nothing happens and you can sign in another way. **Continue** (email and password) and **Phone number** keep working as before.

The **Passkey** button only appears when your browser can use passkeys. If you do not see it, see "Browsers that cannot use passkeys" below.

## Add a passkey


1. In the sidebar, open **User Management**, then **Account**, then the **Security** tab.
2. In the **Passkeys** card, click **Add passkey**.
3. In the **Confirm it's you** dialog, prove who you are:
   * If you have a password, type it.
   * If you do not have a password, click **Send code** and type the 6-digit code sent to your phone. If you have both, the **Use a phone code instead** link switches to the code.
4. Click **Continue**. Your device then asks for Face ID, Touch ID or your fingerprint. Confirm.
5. A **Passkey added** message appears and the passkey shows in the list.

Each passkey is named after the device it was made on, for example "Safari on iPhone". Each row shows when it was added and when it was last used (or **Never used**).

## Rename a passkey


1. In the **Passkeys** card, open the row's menu (the three dots) and choose **Rename**.
2. Type the new name and click **Save**. Save stays disabled while the name is blank.

## Remove a passkey


1. Open the row's menu and choose **Remove**.
2. The button becomes a countdown labelled **Removing**. Click **Cancel** within the countdown to keep the passkey. There is no confirmation dialog.
3. When the countdown ends the passkey is removed, even if you close the page.

## Lost device or new phone

* Sign in another way (**Continue** with your password, or **Phone number**), then go to **User Management**, **Account**, **Security**, **Passkeys** and **Remove** the old device's passkey.
* On the new phone, click **Add passkey** to make a fresh one. A passkey does not move to a new device by itself, unless your phone's own passkey sync (such as iCloud Keychain or Google Password Manager) carries it over.
* If you cannot sign in at all, ask an admin to remove your passkeys (see below).

## Browsers that cannot use passkeys

On a browser or address that cannot use passkeys, the round **Passkey** button is hidden and **Add passkey** is disabled with the note "This browser can't use passkeys." Try an up-to-date Safari, Chrome, Edge or Firefox, and open the CRM from its normal secure (https) address. You can always sign in with email and password or **Phone number**.

## A passkey works only on the address it was made on

A passkey is tied to the exact web address of the CRM where you made it. If you open the CRM from a different address (for example a test copy), your passkey will not be offered there. Add a separate passkey on that address if you need one.

## For admins

### Turn passkey sign-in on or off for a person


1. Go to **User Management**, open the user, and find the **Sign-in** card.
2. Switch **Passkey sign-in** on (or off). A message confirms **Passkey sign-in turned on** or **Passkey sign-in turned off**.

You need the permission to edit users. Without it the row reads **On** or **Off** and cannot be changed.

It is **Off** by default. While it is off the person does not see the **Passkeys** card on their **Account** page, and cannot sign in with a passkey. Turning it off does not delete the passkeys they already made; they work again if you turn it back on.

### See and remove a person's passkeys


1. In the same **Sign-in** card, the **Passkeys** row shows how many the person has (for example "2 passkeys") or **None**.
2. Click the count to open a list showing each passkey's name, when it was added and when it was last used.
3. To remove one, open its row menu and choose **Remove**. It uses the same countdown with **Cancel**.

Removing a passkey is the right step when someone loses a phone. Admins cannot add or rename a person's passkey. The card's **Last sign-in** line shows "passkey" when that was the method used.

## See also

* [Manage users and roles](manage-users-and-roles.md)
* [Getting started for new users](../_shared/getting-started-for-new-users.md)
