# UAC: PS-QUOTE-VIEWS

1. Opening the sign link in a browser that is not signed in to the CRM records one view on that issue.
2. The same browser re-opening the same issue within 30 minutes of its last counted view adds nothing.
3. After 30 minutes it counts again. A different browser counts at once.
4. A request whose user agent is a link-preview bot (WhatsApp, facebookexternalhit, Slackbot, TelegramBot,
   Twitterbot, LinkedInBot, Googlebot, bingbot, generic "bot"/"crawler"/"spider"/"preview") records nothing.
5. A browser signed in to the CRM sends no beacon.
6. An unknown or expired token answers 404 `quotation_sign_link_invalid` and records nothing.
7. Stored per view: issue, company, time, device (mobile/tablet/desktop), hashed browser id. No IP, no user
   agent.
8. The document page shows "Viewed N times, last <date time>" for the latest issue, "Not viewed yet" when
   issued with no views, nothing before the first issue.
9. The document page lists the view log newest first: time, revision, device.
