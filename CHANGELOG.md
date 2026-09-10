# Changelog

All notable changes to the Show Me The Money plugin are documented here.

## [0.1.0] — 2026-09-10

First release.

### Added
- **A "Require payment" switch on protected event menu entries.** Indico counts
  an awaiting-payment registration as participation, so a menu entry protected
  by *Registered participants* opens the moment somebody submits the
  registration form — before the fee is paid. With the switch on, a user whose
  only route into the entry is that registration form is kept out until their
  registration reaches *Completed*. Anyone the access control list admits for
  another reason is unaffected, as are speakers granted access on the entry,
  event managers and Indico admins.
- **Blocked users are told why, with a link to pay.** A message box at the top
  of every event page names how many pages are being withheld, and the page's
  own URL answers with the same message and a link to the user's registration
  rather than a bare 403.
- The requirement is stored per menu entry and cascades with it in the database,
  so deleting an entry — or turning menu customization off, which deletes all of
  them without notice — leaves nothing behind. Enabling and disabling it is
  written to the event log, since disabling it is what opens a page.

### Notes
- The gate covers the menu entry, not the content behind it: a link entry's
  target enforces its own access, and files embedded in a page keep their own
  access control lists.
- Only entries protected in their own right are gated. An inheriting entry is
  decided by its parent, and a gated parent covers its inheriting children.
- Disabling the plugin removes every gate silently — the enforcement lives in
  the plugin, not in the menu entry.
- On events taking payment by bank transfer or on site, nobody reaches
  *Completed* until a manager marks the registration paid.
