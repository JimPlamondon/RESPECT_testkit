# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional

from .android_runtime_runner import (
    DRIVER_PACKAGE,
    GESTURE_PACKAGE,
    RUNTIME_RECEIPT_VERSION,
)
from .resources import resource_path


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _tree_hash(root: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        hasher.update(path.relative_to(root).as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def build_runtime_driver(
    gradle_wrapper: Path,
    output_apk: Path,
    *,
    output_gesture_apk: Optional[Path] = None,
    receipt_path: Optional[Path] = None,
    offline: bool = False,
) -> Dict[str, object]:
    gesture_output = output_gesture_apk or output_apk.with_name(
        f"{output_apk.stem}-gesture{output_apk.suffix}"
    )
    wrapper = gradle_wrapper.resolve(strict=True)
    if not wrapper.is_file():
        raise ValueError("Gradle wrapper must be a file")
    with resource_path("data/android/native-runtime-driver") as source:
        source_hash = _tree_hash(source)
        with tempfile.TemporaryDirectory(prefix="respect-runtime-driver-") as temp:
            project = Path(temp) / "project"
            shutil.copytree(source, project)
            command = [str(wrapper), "-p", str(project), "assembleDebug", "--no-daemon"]
            if offline:
                command.append("--offline")
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
                env=os.environ.copy(),
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    "runtime driver build failed: "
                    f"exit={completed.returncode}, stderr={completed.stderr.strip()}"
                )
            built = project / "app/build/outputs/apk/debug/app-debug.apk"
            if not built.is_file():
                raise RuntimeError("runtime driver build produced no APK")
            built_gesture = (
                project / "gesture/build/outputs/apk/debug/gesture-debug.apk"
            )
            if not built_gesture.is_file():
                raise RuntimeError(
                    "runtime driver build produced no gesture injector APK"
                )
            output_apk.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(built, output_apk)
            gesture_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(built_gesture, gesture_output)
    receipt = {
        "artifact_type": "respect_native_android_runtime_driver_build_receipt",
        "format_version": RUNTIME_RECEIPT_VERSION,
        "driver_package": DRIVER_PACKAGE,
        "gesture_package": GESTURE_PACKAGE,
        "source_tree_sha256": source_hash,
        "apk_sha256": _sha256(output_apk),
        "gesture_apk_sha256": _sha256(gesture_output),
        "gesture_apk_filename": gesture_output.name,
    }
    destination = receipt_path or output_apk.with_suffix(".receipt.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the suite-owned native Android runtime-driver APK."
    )
    parser.add_argument("--gradle-wrapper", type=Path, required=True)
    parser.add_argument("--output-apk", type=Path, required=True)
    parser.add_argument("--output-gesture-apk", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        receipt = build_runtime_driver(
            args.gradle_wrapper,
            args.output_apk,
            output_gesture_apk=args.output_gesture_apk,
            receipt_path=args.receipt,
            offline=args.offline,
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
