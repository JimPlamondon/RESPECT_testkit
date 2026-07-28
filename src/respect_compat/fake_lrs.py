# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass, field
from typing import Dict, List

from .security_labels import SecurityContext


@dataclass
class FakeLrs:
    context: SecurityContext
    statements: List[Dict[str, object]] = field(default_factory=list)

    def receive(self, statement: Dict[str, object]) -> Dict[str, object]:
        missing = [field_name for field_name in ("actor", "verb", "object") if field_name not in statement]
        if missing:
            return {"accepted": False, "mode": self.context.mode, "error": f"missing {', '.join(missing)}"}
        self.statements.append(statement)
        return {"accepted": True, "mode": self.context.mode, "statement_index": len(self.statements) - 1}

    def reset(self) -> None:
        self.statements.clear()
