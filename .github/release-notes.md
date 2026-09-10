Requires **Indico 3.3 or newer**. The plugin has no frontend build, so the wheel
below is all there is to install — no Node.js and no Indico source checkout.

```bash
pip install https://github.com/@REPO@/releases/download/@TAG@/@WHEEL@
indico db --plugin showmethemoney upgrade
```

Add `showmethemoney` to `PLUGINS` in `indico.conf` and restart Indico. Nothing
changes anywhere until a manager turns it on for a menu entry: in an event, go to
**Layout → Menu**, edit a custom page or link, set its protection to *Protected*
with the registration form in the access control list, and switch on **Require
payment**. Registrants whose registration has not reached *Completed* then lose
the entry, and are told why with a link to pay.

Note that disabling the plugin later removes every gate silently — the
enforcement lives here, not in the menu entry.
