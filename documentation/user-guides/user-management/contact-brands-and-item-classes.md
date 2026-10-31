# Contact brands and allowed item classes

Use this to limit which products a dealer contact (and the chatbot answering them) can see: by
**brand**, and within those brands by **item class**. You can set it on one contact, or on a
contact tag so every contact carrying the tag gets it.

## On one contact

1. Open **Users & Access > People > Contacts** and open the contact.
2. In the **Brands** section, pick the brands in **Brands** (empty placeholder **All brands**
   means no brand limit).
3. Under it, pick the classes in **Allowed item classes** (placeholder **All classes**). An empty
   list means every class.
4. Click **Save**: *Brands saved*.

## On a contact tag

1. Open **Users & Access > Access > Contact Tags** and open the tag.
2. In the **Access settings** card, **Brands** group, switch on **Set brands** (when off it reads
   *Brands not set* and the tag does not touch brands).
3. Choose **All brands** or pick brands, then pick **Allowed item classes**.
4. Save: *Tag settings saved*. Contacts with the tag update straight away.

## How the class list works

* **No class** in the list covers products that have no item class. The first class you pick into
  an empty list ticks **No class** for you; untick it if those products should be hidden.
* The class list works whether brands are limited or not, and also for unbranded products.
* When a contact has several tags with class lists, only the classes **all** of them allow apply.
  If they share none, the tags conflict and nothing is written.
* Copying a contact's access copies its class list too.
* A contact limited only by class (no brand list) still gets the unpaid report and the project
  forecast; a brand list blocks both, as before.

You need **Edit Contacts** to change either place.

## Item classes in use cannot be deleted

Under **Products > Reference Data > Item Classes**, a class that products carry and that a
contact or tag limits by cannot be deleted or have its code changed: *Cannot delete this item
class: products carry it and N contacts or tags limit item classes.*

## See also

* [Contact chatbot card](contact-chatbot-card.md)
* [Manage users and roles](manage-users-and-roles.md)
