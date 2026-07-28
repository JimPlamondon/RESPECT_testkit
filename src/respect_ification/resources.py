# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from importlib_resources import files


def resource(relative: str):
    return files("respect_ification").joinpath(*relative.split("/"))
