# UAC: photo-first look-ahead

- PF-1: A text whose turn is running when a photo of the same contact is queued gives way
  before it writes state or posts: the photo is answered first, then the text, even when
  the photo was sent after the text.
- PF-2: A photo queued after the text's look-ahead already passed does not stop the text:
  the text is answered, then the photo.
- PF-3: With two texts queued and one photo, the photo is answered before the queued texts;
  the texts keep their send order.
- PF-4: With no photo queued, nothing changes and nothing waits.
- PF-5: A photo of another contact never affects this contact's order.
- PF-6: A voice note is not a photo: queued behind a running text, it is answered after it
  (owner, 25 Oct: "Photo only").
- PF-7: A photo goes first only for its first 60 s in the queue. Past that (a read that
  will not finish), it takes its send-order place: a text sent EARLIER than the photo is
  answered (about 60 to 90 s after the photo was queued: 60 s plus one photo-read poll); a
  text sent after it still waits in send order, as before this lane (owner, 25 Oct: "1a ok").
- PF-8: The photo's reply and the text's reply are two messages, photo first (owner,
  25 Oct: "2b two msg is ok").
