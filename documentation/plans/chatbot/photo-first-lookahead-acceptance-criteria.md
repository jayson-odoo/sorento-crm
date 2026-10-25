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
