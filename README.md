# Show Me The Money

An Indico plugin that withholds a registrant-only menu entry until the
registration fee has actually been paid.

## The problem it solves

An event menu entry can be protected with an access control list containing a
registration form — the "Registered participants" principal. Indico counts an
**awaiting-payment** registration as participation, so on a paid event the entry
opens the moment somebody submits the registration form, before any money moves.
An organiser who puts a paid-attendee-only page behind "Registered participants"
is not getting what the label suggests.

This plugin adds a **Require payment** switch to the menu entry's settings. With
it on, a user whose only route into the entry is that registration form is denied
until their registration reaches the *Completed* state.

## Using it

1. Enable `showmethemoney` in `PLUGINS` in `indico.conf` and run
   `indico db --all-plugins upgrade`.
2. In an event: *Layout » Menu*, edit a custom page or link, set **Protection
   mode** to *Protected*, add the registration form to the access control list,
   and turn on **Require payment**.

The switch appears only for custom pages and links — the entries that have an
access control list of their own — and only while the entry is protected in its
own right. Turning protection back to *Inheriting* clears the requirement,
because an inheriting entry's own ACL is never consulted.

## What a blocked user sees

The entry disappears from the menu, as any entry does when a user cannot access
it. Because that leaves nothing to click, two things explain the absence:

- a message box at the top of every event page — *"One page in this event stays
  hidden until your registration payment is complete"* — with a **Pay now** link
  to their registration;
- the same message, and the same link, if they reach the page's URL directly from
  a bookmark or an email.

## Limits worth knowing

**It gates the menu entry, not the content behind it.** For a *link* entry the
plugin hides the link; whatever the link points at enforces its own access, or
none. For a *page* entry, images and files embedded in the page are attachments
with their own access control lists — gating the page does not gate the PDF.

**It covers menu entries only.** The same "unpaid counts as registered" semantics
apply to event, session, contribution and attachment ACLs. Those are untouched.
Gating the event itself is deliberately not offered: on a protected event whose
ACL holds the registration form, denying an unpaid registrant would also shut them
out of their own registration and payment pages, and they could never pay their
way back in.

**Only self-protected entries are gated.** An entry set to *Inheriting* is decided
entirely by its parent. A gated *parent* entry does cascade to its inheriting
children; a child with its own protection and its own ACL needs its own switch.

**Managers, speakers and admins are never blocked**, nor is anyone the ACL admits
for a reason other than the registration form.

**"Paid" means the registration is Completed.** On events that take payment by
bank transfer or on site, nobody reaches that state until a manager marks the
registration paid, so registrants stay blocked until then. If an event's payment
feature is switched off while unpaid registrations exist, those registrations stay
*Awaiting payment* indefinitely — Indico still admits them to the event, but this
plugin will keep them out of gated pages until a manager marks them paid or the
price is set to zero.

**Disabling the plugin removes every gate**, silently and immediately: the
enforcement lives in the plugin, not in the entry. The switch's settings survive,
so re-enabling restores them.

**Event import does not carry the flag.** An imported event arrives with its ACL
intact and its gates missing. Cloning is unaffected — a cloned protected entry
starts with an empty ACL, so it admits nobody until the ACL is rebuilt.

## Requirements

Indico 3.3 or newer. No frontend build, no extra runtime dependencies.

## License

MIT — see `LICENSE`.
