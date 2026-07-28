# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from importlib_resources import as_file, files


def resource(relative: str):
    return files("respect_compat").joinpath(*relative.split("/"))


@contextmanager
def resource_path(relative: str) -> Iterator[Path]:
    with as_file(resource(relative)) as materialized:
        yield materialized
