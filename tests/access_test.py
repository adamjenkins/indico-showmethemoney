# This file is part of the Show Me The Money plugin for Indico.
# Copyright (C) 2026 Adam Jenkins
#
# The Show Me The Money plugin is free software; you can redistribute
# it and/or modify it under the terms of the MIT License;
# see the LICENSE file for more details.

import pytest

from indico.core.db.sqlalchemy.protection import ProtectionMode
from indico.modules.events.layout.models.menu import EventPage, MenuEntry, MenuEntryType
from indico.modules.events.registration.models.registrations import Registration, RegistrationState

from indico_showmethemoney.access import payment_blocks_access, set_gated
from indico_showmethemoney.plugin import ShowmethemoneyPlugin


#: Registration fixtures are not loaded by default, and this has to be at module
#: level -- pytest ignores `pytest_plugins` in a nested conftest.
pytest_plugins = ('indico.modules.events.registration.testing.fixtures',)


@pytest.fixture
def protected_entry(db, dummy_event, dummy_regform):
    """A protected custom page whose ACL admits registrants of the dummy regform."""
    page = EventPage(html='<p>Members only</p>')
    dummy_event.custom_pages.append(page)
    entry = MenuEntry(event=dummy_event, type=MenuEntryType.page, title='Members only', page=page,
                      protection_mode=ProtectionMode.protected, position=0, is_enabled=True)
    db.session.add(entry)
    db.session.flush()
    entry.update_principal(dummy_regform, read_access=True)
    db.session.flush()
    return entry


@pytest.fixture
def gated_entry(db, protected_entry):
    set_gated(protected_entry, True)
    db.session.flush()
    return protected_entry


@pytest.fixture
def register(db, dummy_event, dummy_regform):
    """Register a user for the dummy event in a given state.

    Core's own `create_registration` fixture cannot do this: it hardcodes
    `state=complete` and forwards **kwargs, so asking for any other state is a
    TypeError -- and "awaiting payment" is the whole point here.
    """
    def _register(user, state):
        registration = Registration(first_name='Guinea', last_name='Pig', currency='USD', email=user.email,
                                    user=user, registration_form=dummy_regform, state=state)
        dummy_event.registrations.append(registration)
        db.session.flush()
        return registration

    return _register


def test_unpaid_registrant_is_denied(gated_entry, dummy_user, register):
    register(dummy_user, RegistrationState.unpaid)
    assert not gated_entry.can_access(dummy_user)


def test_completed_registrant_is_allowed(gated_entry, dummy_user, register):
    register(dummy_user, RegistrationState.complete)
    assert gated_entry.can_access(dummy_user)


def test_unpaid_registrant_is_allowed_when_not_gated(protected_entry, dummy_user, register):
    register(dummy_user, RegistrationState.unpaid)
    assert protected_entry.can_access(dummy_user)


def test_gated_entry_is_hidden_from_the_menu(gated_entry, dummy_user, register, request_context):
    from flask import session
    register(dummy_user, RegistrationState.unpaid)
    session.set_session_user(dummy_user)
    assert not gated_entry.is_visible


def test_admin_is_never_denied(db, gated_entry, register, create_user):
    admin = create_user(1338, admin=True)
    register(admin, RegistrationState.unpaid)
    assert gated_entry.can_access(admin)


def test_event_manager_is_never_denied(db, gated_entry, dummy_user, dummy_event, register):
    register(dummy_user, RegistrationState.unpaid)
    dummy_event.update_principal(dummy_user, full_access=True)
    db.session.flush()
    assert gated_entry.can_access(dummy_user)


def test_explicit_acl_entry_wins_over_an_unpaid_registration(db, gated_entry, dummy_user, register):
    register(dummy_user, RegistrationState.unpaid)
    gated_entry.update_principal(dummy_user, read_access=True)
    db.session.flush()
    assert gated_entry.can_access(dummy_user)


def test_core_forbids_a_second_live_registration(db, gated_entry, dummy_user, register):
    # `settled_registrations` folds duplicates with "completed wins" so that a
    # stale row can never deny a paid-up user. That defence is unreachable while
    # core keeps its partial unique index on (registration_form_id, user_id) --
    # this test fails if that ever changes, so the folding stops being dead code
    # and starts being load-bearing.
    from sqlalchemy.exc import IntegrityError
    register(dummy_user, RegistrationState.unpaid)
    with pytest.raises(IntegrityError):
        register(dummy_user, RegistrationState.complete)
    db.session.rollback()


def test_pending_registration_is_denied_by_core_not_by_us(db, gated_entry, dummy_user, register):
    # Core's principal excludes pending registrations outright, so the entry is
    # closed to them anyway -- and this plugin must not be what decides it.
    registration = register(dummy_user, RegistrationState.pending)
    assert not gated_entry.can_access(dummy_user)
    assert payment_blocks_access(gated_entry, dummy_user) is None
    assert registration.state == RegistrationState.pending


def test_inheriting_entry_is_never_gated(db, gated_entry, dummy_user, register):
    register(dummy_user, RegistrationState.unpaid)
    gated_entry.protection_mode = ProtectionMode.inheriting
    db.session.flush()
    assert payment_blocks_access(gated_entry, dummy_user) is None


def test_receiver_stays_silent_in_the_early_phase(gated_entry, dummy_user, register):
    # Returning False before core has run its own checks would pre-empt the admin
    # check and lock out Indico admins.
    register(dummy_user, RegistrationState.unpaid)
    plugin = ShowmethemoneyPlugin.instance
    assert plugin._veto_unpaid_access(MenuEntry, obj=gated_entry, user=dummy_user, authorized=None) is None
    assert plugin._veto_unpaid_access(MenuEntry, obj=gated_entry, user=dummy_user, authorized=False) is None
    assert plugin._veto_unpaid_access(MenuEntry, obj=gated_entry, user=dummy_user, authorized=True) is False


def test_gate_disappears_with_the_menu_entry(db, gated_entry, dummy_event):
    from indico_showmethemoney.models.gating import GatedMenuEntry
    entry_id = gated_entry.id
    db.session.delete(gated_entry)
    db.session.flush()
    assert GatedMenuEntry.query.filter_by(menu_entry_id=entry_id).first() is None


def test_cloned_entry_has_no_acl(db, dummy_event, protected_entry, create_event):
    # The clone is fail-closed today because core copies column attributes only,
    # leaving the ACL empty. If core ever starts cloning ACL rows, this test fails
    # and the missing gate on a clone becomes a decision rather than a surprise.
    from indico.modules.events.layout.clone import LayoutCloner
    new_event = create_event()
    LayoutCloner(dummy_event).run(new_event, {}, {}, False)
    db.session.flush()
    cloned = MenuEntry.query.with_parent(new_event).filter_by(title='Members only').first()
    if cloned is not None:
        assert not cloned.acl_entries


def test_switch_is_injected_and_seeded_from_the_entry(app, gated_entry, protected_entry, dummy_event):
    # `default=` on an injected field is silently ignored for these forms, because
    # FormDefaults answers for any attribute name. If the seeding through the
    # defaults object ever breaks, the switch renders off for a gated entry and
    # the next save turns the gate off -- silently. Hence this test.
    from indico.modules.events.layout.forms import MenuPageForm
    from indico.web.forms.base import FormDefaults
    with app.test_request_context():
        form = MenuPageForm(entry=gated_entry, obj=FormDefaults(gated_entry), event=dummy_event,
                            editor_upload_url='/dummy')
        assert form.ext__require_payment.data is True


def test_switch_is_off_for_an_ungated_entry(app, protected_entry, dummy_event):
    from indico.modules.events.layout.forms import MenuPageForm
    from indico.web.forms.base import FormDefaults
    with app.test_request_context():
        form = MenuPageForm(entry=protected_entry, obj=FormDefaults(protected_entry), event=dummy_event,
                            editor_upload_url='/dummy')
        assert form.ext__require_payment.data is False
