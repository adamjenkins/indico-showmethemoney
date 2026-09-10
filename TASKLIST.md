# Tasklist

## Done

- Access veto on `signals.acl.can_access` for menu entries: denies only when the
  user's route in is a registration form and the registration is not complete.
- `Require payment` switch injected into the menu entry dialogs (link and page),
  seeded from the stored flag, cleared when the entry stops being self-protected.
- Flag stored in `plugin_showmethemoney.gated_menu_entries`, cascading with the
  menu entry at the database level.
- Message box on event pages and a redirect with an explanation on the page URL.
- 15 tests, and browser verification on the dev instance: the switch renders,
  seeds and saves from both the edit and the add dialog; an unpaid registrant
  loses the menu entry, sees the message box and is redirected from the page URL
  to their registration; marking the registration paid restores all three.

## Open

- No speaker-path test (`speakers_can_access`) -- covered by code inspection only.
- Not verified with a real payment plugin; the paid state was reached by a manager
  marking the registration paid, which is the same state transition.
- No German/French translations; strings are marked but no catalogue is shipped.
