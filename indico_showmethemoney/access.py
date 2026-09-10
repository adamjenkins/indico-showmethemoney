# This file is part of the Show Me The Money plugin for Indico.
# Copyright (C) 2026 Adam Jenkins
#
# The Show Me The Money plugin is free software; you can redistribute
# it and/or modify it under the terms of the MIT License;
# see the LICENSE file for more details.

"""Deciding whether an unpaid registration costs a user access to a menu entry.

Core counts an awaiting-payment registrant as a member of the "Registered
participants" principal -- ``RegistrationForm.__contains__`` matches both
``RegistrationState.unpaid`` and ``RegistrationState.complete`` -- so registering
for a paid event grants access before any money moves. Everything here exists to
take that access back for one menu entry at a time, and to take it back from
nobody else.
"""

from flask import has_request_context, session

from indico.core.db import db
from indico.core.db.sqlalchemy.principals import PrincipalType
from indico.core.db.sqlalchemy.protection import ProtectionMode
from indico.modules.events.layout.models.menu import MenuEntry
from indico.modules.events.registration.models.forms import RegistrationForm
from indico.modules.events.registration.models.registrations import Registration, RegistrationState
from indico.modules.logs.models.entries import EventLogRealm, LogKind
from indico.util.caching import memoize_request
from indico.util.user import iter_acl

from indico_showmethemoney.models.gating import GatedMenuEntry


@memoize_request
def gated_entry_ids(event):
    """The ids of the event's menu entries that require payment."""
    query = db.session.query(GatedMenuEntry.menu_entry_id).filter(GatedMenuEntry.event_id == event.id)
    return {menu_entry_id for menu_entry_id, in query}


@memoize_request
def settled_registrations(event, user):
    """The user's registrations for the event that core counts as participation.

    Keyed by registration form id, mirroring which states
    ``RegistrationForm.__contains__`` accepts: anything else (pending, rejected,
    withdrawn) is not a member of the principal in the first place, so core
    denies access before this plugin is ever consulted.

    A completed registration wins over an unpaid one for the same form, so that a
    stale row could never deny a paid-up user. Core's partial unique index on
    (registration_form_id, user_id) means that cannot happen today; the fold is
    here so that it still could not if the index ever went away.
    """
    if user is None:
        return {}
    registrations = (Registration.query
                     .filter(Registration.user_id == user.id,
                             Registration.event_id == event.id,
                             ~Registration.is_deleted,
                             Registration.state.in_((RegistrationState.unpaid, RegistrationState.complete)))
                     .join(Registration.registration_form)
                     .filter(~RegistrationForm.is_deleted)
                     .all())
    settled = {}
    for registration in registrations:
        current = settled.get(registration.registration_form_id)
        if current is None or current.state != RegistrationState.complete:
            settled[registration.registration_form_id] = registration
    return settled


def blocking_registration(entry, user):
    """The unpaid registration that costs `user` access to `entry`, or ``None``.

    ``None`` means this plugin has nothing to say about the entry: either it is
    not gated, or the user's access does not come from a registration form, or
    they have paid. It deliberately does *not* consider admins or managers --
    `payment_blocks_access` layers those exemptions on top, so that every caller
    applies them identically.
    """
    if user is None or entry.id is None:
        return None
    # Only an entry protected in its own right has an ACL that is consulted at
    # all: `inheriting_have_acl` is False for menu entries, so an inheriting
    # entry is decided entirely by its parent -- and a gated *parent* already
    # cascades, because its own access check re-fires the same signal.
    if entry.protection_mode != ProtectionMode.protected:
        return None
    event = entry.event_ref
    if entry.id not in gated_entry_ids(event):
        return None

    acl = list(entry.acl_entries)
    regform_ids = {e.registration_form_id for e in acl if e.type == PrincipalType.registration_form}
    if not regform_ids:
        return None
    # Anyone the entry admits for a reason of their own keeps that access. A menu
    # entry ACL can only hold users, groups, event roles, category roles and
    # registration forms, so this covers every non-payment route into it.
    for acl_entry in iter_acl(e for e in acl if e.type != PrincipalType.registration_form):
        if user in acl_entry.principal:
            return None
    if entry.speakers_can_access and event.is_user_speaker(user):
        return None

    settled = settled_registrations(event, user)
    matched = [settled[regform_id] for regform_id in regform_ids if regform_id in settled]
    if not matched:
        # The registration forms in this ACL are not why the user is here. Say
        # nothing rather than guess: an ACL row pointing at another event's form
        # (possible in imported data) must not deny anyone.
        return None
    if any(registration.state == RegistrationState.complete for registration in matched):
        return None
    return matched[0]


def payment_blocks_access(entry, user, allow_admin=True):
    """The registration `user` must pay before `entry` opens to them, or ``None``.

    The single predicate behind the access veto, the page redirect and the header
    message, so that all three agree about who is being kept out.
    """
    if user is None:
        return None
    if allow_admin and user.is_admin:
        return None
    registration = blocking_registration(entry, user)
    if registration is None:
        return None
    # Event managers are exempt deliberately. Core already denies a manager who is
    # not in a protected entry's ACL, so this only affects one whose sole way in
    # was their own registration -- and locking an organiser out of their own page
    # is worse than letting one through. It costs a walk up the category chain,
    # which is why it is the last check rather than the first.
    if event_manager_exempt(entry, user, allow_admin=allow_admin):
        return None
    return registration


def event_manager_exempt(entry, user, allow_admin=True):
    return entry.event_ref.can_manage(user, allow_admin=allow_admin)


def blocked_entries(event, user):
    """Every gated entry of the event that `user` is currently kept out of."""
    if user is None:
        return []
    entry_ids = gated_entry_ids(event)
    if not entry_ids:
        return []
    blocked = []
    for entry in MenuEntry.query.filter(MenuEntry.id.in_(entry_ids)):
        registration = payment_blocks_access(entry, user)
        if registration is not None:
            blocked.append((entry, registration))
    return blocked


def is_gated(entry):
    return entry.id is not None and _gate_row(entry) is not None


def set_gated(entry, gated):
    """Add or remove the entry's payment gate, logging the change on the event.

    Logged explicitly because core cannot: the menu entry log writes a fixed set
    of fields from ``form.data``, which drops injected plugin fields. Without
    this there would be no record of who turned a gate off, and turning one off
    is the change that opens a page.
    """
    row = _gate_row(entry)
    if gated and row is None:
        db.session.add(GatedMenuEntry(menu_entry_id=entry.id, event_id=entry.event_id))
        _log_change(entry, enabled=True)
    elif not gated and row is not None:
        db.session.delete(row)
        _log_change(entry, enabled=False)


def _gate_row(entry):
    return GatedMenuEntry.query.filter_by(menu_entry_id=entry.id).first()


def _log_change(entry, enabled):
    # No user outside a request: the flag can also be set from a script or a
    # shell, and an unattributed log entry beats no log entry at all.
    user = session.user if has_request_context() else None
    entry.log(EventLogRealm.management, LogKind.positive if enabled else LogKind.negative, 'Menu',
              'Menu entry payment requirement {}: {}'.format('enabled' if enabled else 'disabled', entry.log_title),
              user)
