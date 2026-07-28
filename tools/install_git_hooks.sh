#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
git -C "${repo_root}" config core.hooksPath .githooks
printf 'Configured core.hooksPath=.githooks\n'
