# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
from importlib.resources import files
from typing import Any, Dict


def load_schema(name: str) -> Dict[str, Any]:
    return json.loads(
        files("respect_upgrade_dossier")
        .joinpath("data/schemas", name)
        .read_text(encoding="utf-8")
    )
