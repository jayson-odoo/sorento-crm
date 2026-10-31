# MCP access token (Settings > Integrations)

Use this when you connect n8n (or another tool) to the CRM's MCP server, or when the token must
change because it may have leaked or someone who knew it left. The MCP server lets those tools
read CRM data; every call must carry this token. You set it here on screen; nobody edits a
server file any more.

## Where to find it

**Users & Access > Settings**, **Integrations** tab (`/user-management/settings/integrations`),
card **MCP access token**.

You need **View Settings** to open the page and **Manage integration secrets** to see the card.
Without the second one the card is not shown at all.

## Read the card

* A status badge: **Set**, **Not set**, or **Saved token unreadable, rotate it**.
* The saved token, masked (`****` and its last 4 characters), and **Last generated {date}**.
* **Enforce**: when on, a call without the token is refused. When off, a call with no token is
  still answered (a wrong token is always refused).
* After a rotate: **Previous token valid until {date}**.

## Set the token for the first time

1. Click **Generate token**. You see *MCP token generated*.
2. The new token shows once, under **New token, shown once**. Click the copy icon (**Copy MCP
   token**): *MCP token copied*. If copying fails (*Could not copy the token*), select and copy it
   by hand.
3. Paste it into n8n (the MCP credential's bearer token).
4. Switch **Enforce** on: *Enforce updated*.

The token is shown only this once. **Hide token** removes it from the screen for good, and so does
leaving the page. If you lose it before pasting it, rotate.

## Change (rotate) the token

1. Click **Rotate token** and copy the new token as above.
2. Paste the new token into n8n.
3. The old token keeps working for **24 hours** so nothing breaks while you update n8n. When n8n
   uses the new one, click **Revoke previous now** to end the old one early.

If you click **Revoke previous now** a few seconds after rotating you may see *The new token is
still being picked up; try again in a few seconds.* Wait and click again.

## Things that can stop you

* **Enforce** is greyed out until a token is set (or while the saved one is unreadable): *Generate
  or rotate the token before switching Enforce on.*
* **Saved token unreadable, rotate it**: the stored token can no longer be read (for example
  after a server key change). Click **Rotate token** and update n8n.
* If the card cannot load, it shows the error and a **Retry** button.

## See also

* [Manage users and roles](manage-users-and-roles.md)
* [Chatbot settings](chatbot-settings.md)
