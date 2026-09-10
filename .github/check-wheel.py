#!/usr/bin/env python3
# This file is part of the Show Me The Money plugin for Indico.
# Copyright (C) 2026 Adam Jenkins
#
# The Show Me The Money plugin is free software; you can redistribute
# it and/or modify it under the terms of the MIT License;
# see the LICENSE file for more details.

"""Check the built wheel actually contains the files the plugin needs at runtime.

The message box template and the migration are package data. Nothing imports
them, so nothing fails at install time if the packaging config stops including
them: the plugin loads, `indico db upgrade` has no schema to create, and the
first event page a blocked registrant opens raises on a missing template. The
gate itself would still hold -- but the person it shuts out would see a server
error instead of the reason and a link to pay. Cheaper to assert here than to
find out from a site.
"""
import sys
import zipfile
from pathlib import Path


REQUIRED = (
    'indico_showmethemoney/templates/header_message.html',
)

#: Every migration, whatever it is called -- a plugin that ships its schema
#: creation but not a later revision is worse than one that ships neither.
REQUIRED_PREFIXES = ('indico_showmethemoney/migrations/',)

#: Things that have no business being installed on a site.
FORBIDDEN_PREFIXES = ('tests/', 'scripts/')


def main() -> int:
    wheels = sorted(Path('dist').glob('*.whl'))
    if len(wheels) != 1:
        print(f'expected exactly one wheel in dist/, found {[w.name for w in wheels]}')
        return 1

    names = set(zipfile.ZipFile(wheels[0]).namelist())
    problems = [f'missing: {name}' for name in REQUIRED if name not in names]

    for prefix in REQUIRED_PREFIXES:
        found = sum(1 for name in names if name.startswith(prefix) and name.endswith('.py'))
        if not found:
            problems.append(f'no files under {prefix}')

    problems += [f'should not be packaged: {name}' for name in sorted(names)
                 if name.startswith(FORBIDDEN_PREFIXES)]

    print(f'{wheels[0].name}: {len(names)} entries')
    for problem in problems:
        print(f'  {problem}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
