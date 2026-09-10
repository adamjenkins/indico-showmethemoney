# This file is part of the Show Me The Money plugin for Indico.
# Copyright (C) 2026 Adam Jenkins
#
# The Show Me The Money plugin is free software; you can redistribute
# it and/or modify it under the terms of the MIT License;
# see the LICENSE file for more details.

from indico.core.db import db
from indico.util.string import format_repr


class GatedMenuEntry(db.Model):
    """A menu entry that withholds access until the registration fee is paid.

    A row per gated entry, rather than a list of entry ids in the plugin's
    settings, because core destroys menu entries without telling anyone: turning
    menu customization off deletes every entry of an event in a loop, and
    deleting one entry is a hard delete -- neither path emits a signal a plugin
    could listen to. The foreign key's ``ON DELETE CASCADE`` is what keeps this
    table honest across both, and it has to be a database-level cascade rather
    than an ORM one, since the ORM relationship does not exist at all while the
    plugin is disabled -- and a menu entry must stay deletable then.

    Presence of the row is the flag; there is no boolean column. An entry with no
    row here behaves exactly as it does without this plugin installed.
    """

    __tablename__ = 'gated_menu_entries'
    __table_args__ = {'schema': 'plugin_showmethemoney'}

    menu_entry_id = db.Column(
        db.Integer,
        db.ForeignKey('events.menu_entries.id', ondelete='CASCADE'),
        primary_key=True
    )
    #: Denormalized from the menu entry so the access check can fetch an event's
    #: gated ids in one query, without joining core's table on every page render.
    #: Safe to duplicate: an entry never moves between events.
    event_id = db.Column(
        db.Integer,
        db.ForeignKey('events.events.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    def __repr__(self):
        return format_repr(self, 'menu_entry_id', 'event_id')
