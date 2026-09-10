# This file is part of the Show Me The Money plugin for Indico.
# Copyright (C) 2026 Adam Jenkins
#
# The Show Me The Money plugin is free software; you can redistribute
# it and/or modify it under the terms of the MIT License;
# see the LICENSE file for more details.

from flask import flash, g, has_request_context, redirect, session
from flask_pluginengine import render_plugin_template
from markupsafe import Markup
from sqlalchemy import event as sa_event
from werkzeug.exceptions import Forbidden
from wtforms.fields import BooleanField

from indico.core import signals
from indico.core.db import db
from indico.core.db.sqlalchemy.protection import ProtectionMode
from indico.core.plugins import IndicoPlugin
from indico.modules.events.layout.controllers.menu import RHPageDisplay
from indico.modules.events.layout.forms import MenuLinkForm, MenuPageForm, MenuUserEntryFormBase
from indico.modules.events.layout.models.menu import MenuEntry
from indico.web.flask.util import url_for
from indico.web.forms.validators import HiddenUnless
from indico.web.forms.widgets import SwitchWidget

from indico_showmethemoney import _
from indico_showmethemoney.access import blocked_entries, is_gated, payment_blocks_access, set_gated


#: Where the value from the "add menu entry" dialog waits between the form
#: validating and the entry existing. See `_remember_pending_flag`.
_PENDING_FLAG = 'showmethemoney_pending'
#: Where the newly created entry is parked by the flush listener.
_PENDING_ENTRY = 'showmethemoney_new_entry'


class ShowmethemoneyPlugin(IndicoPlugin):
    """Show Me The Money

    Withholds a protected event menu entry from registrants who have not paid.

    Indico counts an awaiting-payment registration as participation, so putting
    a page behind "Registered participants" opens it the moment someone submits
    the registration form -- before the fee is paid. Ticking "Require payment"
    on the entry keeps it shut until the registration is complete.
    """

    def init(self):
        super().init()
        # The enforcement. Everything else in this plugin exists to configure it
        # or to explain it to the person it shuts out.
        self.connect(signals.acl.can_access, self._veto_unpaid_access, sender=MenuEntry)
        # The switch, injected into the two menu entry dialogs that have an ACL.
        # Sender must be the concrete form class: blinker matches senders by
        # identity, so subscribing to their shared base would never fire.
        self.connect(signals.core.add_form_fields, self._add_require_payment_field, sender=MenuLinkForm)
        self.connect(signals.core.add_form_fields, self._add_require_payment_field, sender=MenuPageForm)
        self.connect(signals.core.form_validated, self._store_flag)
        self.connect(signals.core.after_process, self._store_pending_flag)
        # Telling the user why a page they have a link to will not open.
        self.connect(signals.rh.before_check_access, self._redirect_to_payment, sender=RHPageDisplay)
        self.connect(signals.core.app_created, self._extend_app)
        self.template_hook('extra-event-header-msg', self._render_header_message)

    def _extend_app(self, app, **kwargs):
        # The "add menu entry" dialog has no signal to wait for: the layout module
        # emits nothing when an entry is created, and the entry does not exist
        # while the form is validating. Core does flush it inside the request (so
        # it can log the new id), so a flush listener can catch it on the way past.
        # Guarded by `_PENDING_FLAG`, which only the add dialog ever sets.
        sa_event.listen(db.session, 'after_flush', _capture_new_entry)

    def _veto_unpaid_access(self, sender, obj, user, authorized=None, allow_admin=True, **kwargs):
        # This receiver may only ever deny, and only once core has already decided
        # to allow. Returning False in the early phase (authorized is None) would
        # pre-empt core's admin check and lock out Indico admins; returning True in
        # either phase would grant access to anyone, anonymous users included.
        if authorized is not True:
            return None
        if payment_blocks_access(obj, user, allow_admin=allow_admin) is None:
            return None
        return False

    def _add_require_payment_field(self, form_cls, form_args, form_kwargs, **kwargs):
        entry = form_kwargs.get('entry')
        defaults = form_kwargs.get('obj')
        if defaults is not None:
            # `default=` on the field would be silently ignored: both menu entry
            # controllers pass a real object to `FormDefaults`, so `hasattr` is
            # true for any name, wtforms takes `data=None` and never looks at the
            # default. Seeding through the defaults object is what actually
            # reaches the rendered switch -- and getting this wrong would render
            # the switch off for a gated entry and then turn the gate off on save.
            defaults['ext__require_payment'] = entry is not None and is_gated(entry)
        return 'require_payment', BooleanField(
            _('Require payment'),
            [HiddenUnless('protection_mode', ProtectionMode.protected, preserve_data=True)],
            widget=SwitchWidget(),
            description=_('Registrants who have not completed payment are kept out, even though a registration '
                          'form in the access control list would otherwise let them in. Anyone listed in the ACL '
                          'for another reason, and any speaker granted access above, is unaffected.'))

    def _store_flag(self, form, **kwargs):
        if not isinstance(form, MenuUserEntryFormBase):
            return
        field = getattr(form, 'ext__require_payment', None)
        if field is None:
            return
        # The switch is hidden, and its value preserved, whenever the entry is not
        # protected in its own right. Clearing it there stops a stale "on" from
        # surviving a change of protection mode and silently coming back later.
        gated = bool(field.data) and form.protection_mode.data == ProtectionMode.protected
        entry = getattr(g.get('rh'), 'entry', None)
        if entry is not None:
            set_gated(entry, gated)
        else:
            setattr(g, _PENDING_FLAG, gated)

    def _store_pending_flag(self, sender, **kwargs):
        gated = g.pop(_PENDING_FLAG, None)
        entry = g.pop(_PENDING_ENTRY, None)
        if gated is None:
            return
        if entry is None or entry.id is None:
            if gated:
                self.logger.warning('Could not store the payment requirement for a new menu entry: '
                                    'the entry was not seen being created')
            return
        set_gated(entry, gated)

    def _redirect_to_payment(self, sender, rh, **kwargs):
        # This receiver must only ever raise. Returning any value at all -- even
        # True -- makes core skip `_check_access` entirely for this request, which
        # would open the page to everyone.
        registration = payment_blocks_access(rh.page.menu_entry, session.user)
        if registration is None:
            return
        url = url_for('event_registration.display_regform', registration.locator.registrant)
        flash(Markup('{} <a href="{}">{}</a>').format(
            _('This page opens once your registration payment is complete.'), url, _('Pay now')), 'warning')
        raise Forbidden(response=redirect(url))

    def _render_header_message(self, event=None, **kwargs):
        if event is None or session.user is None:
            return None
        blocked = blocked_entries(event, session.user)
        if not blocked:
            return None
        registration = blocked[0][1]
        return render_plugin_template(
            'showmethemoney:header_message.html',
            count=len(blocked),
            url=url_for('event_registration.display_regform', registration.locator.registrant))


def _capture_new_entry(session_, flush_context):
    if not has_request_context() or _PENDING_FLAG not in g:
        return
    for obj in session_.new:
        if isinstance(obj, MenuEntry):
            setattr(g, _PENDING_ENTRY, obj)
