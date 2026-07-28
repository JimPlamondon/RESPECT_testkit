# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree


ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
DEFAULT_JAVA_HOME = (
    Path(os.environ["JAVA_HOME"]).expanduser()
    if os.environ.get("JAVA_HOME")
    else None
)
DEFAULT_APKANALYZER = None
DEFAULT_ADB = None


def parse_manifest_xml(text: str) -> Dict[str, Any]:
    root = ElementTree.fromstring(text)
    package_id = root.attrib.get("package", "")
    app_links: List[Dict[str, Any]] = []
    for activity in root.findall(".//activity"):
        activity_name = activity.attrib.get(f"{ANDROID_NS}name", "")
        exported = activity.attrib.get(f"{ANDROID_NS}exported") == "true"
        for intent_filter in activity.findall("intent-filter"):
            actions = {
                item.attrib.get(f"{ANDROID_NS}name")
                for item in intent_filter.findall("action")
            }
            categories = {
                item.attrib.get(f"{ANDROID_NS}name")
                for item in intent_filter.findall("category")
            }
            for data in intent_filter.findall("data"):
                scheme = data.attrib.get(f"{ANDROID_NS}scheme")
                host = data.attrib.get(f"{ANDROID_NS}host")
                if (
                    "android.intent.action.VIEW" in actions
                    and "android.intent.category.DEFAULT" in categories
                    and "android.intent.category.BROWSABLE" in categories
                    and scheme == "https"
                    and host
                ):
                    app_links.append(
                        {
                            "activity": activity_name,
                            "exported": exported,
                            "scheme": scheme,
                            "host": host,
                            "auto_verify": (
                                intent_filter.attrib.get(f"{ANDROID_NS}autoVerify")
                                == "true"
                            ),
                        }
                    )
    query_actions = sorted(
        {
            action.attrib.get(f"{ANDROID_NS}name")
            for action in root.findall(".//queries/intent/action")
            if action.attrib.get(f"{ANDROID_NS}name")
        }
    )
    return {
        "package_id": package_id,
        "app_links": app_links,
        "query_actions": query_actions,
    }


def inspect_apk(
    apk: Path,
    apkanalyzer: Optional[Path] = None,
    java_home: Optional[Path] = None,
) -> Dict[str, Any]:
    tool = apkanalyzer or DEFAULT_APKANALYZER
    if tool is None or not tool.exists():
        located = shutil.which("apkanalyzer")
        if not located:
            raise FileNotFoundError("apkanalyzer")
        tool = Path(located)
    selected_java = java_home or DEFAULT_JAVA_HOME
    environment = os.environ.copy()
    if selected_java is not None and selected_java.exists():
        environment["JAVA_HOME"] = str(selected_java)
        environment["PATH"] = f"{selected_java / 'bin'}:{environment.get('PATH', '')}"
    completed = subprocess.run(
        [str(tool), "manifest", "print", str(apk)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"apkanalyzer failed with {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    result = parse_manifest_xml(completed.stdout)
    result["apk"] = str(apk.resolve())
    result["apk_size"] = apk.stat().st_size
    android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    build_tools = Path(android_home).expanduser() / "build-tools" if android_home else None
    apksigners = (
        sorted(build_tools.glob("*/apksigner"), reverse=True)
        if build_tools is not None
        else []
    )
    if apksigners:
        signing = subprocess.run(
            [
                str(apksigners[0]),
                "verify",
                "--print-certs",
                str(apk),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        match = re.search(
            r"certificate SHA-256 digest:\s*([0-9a-fA-F]+)",
            signing.stdout,
        )
        result["signer_sha256"] = (
            match.group(1).upper() if match and signing.returncode == 0 else None
        )
    else:
        result["signer_sha256"] = None
    return result


def assetlinks_matches(
    statements: Any,
    package_id: str,
    signer_sha256: str,
) -> bool:
    if not isinstance(statements, list):
        return False
    normalized_signer = signer_sha256.replace(":", "").upper()
    for statement in statements:
        if not isinstance(statement, dict):
            continue
        relation = statement.get("relation")
        target = statement.get("target")
        if (
            isinstance(relation, list)
            and "delegate_permission/common.handle_all_urls" in relation
            and isinstance(target, dict)
            and target.get("namespace") == "android_app"
            and target.get("package_name") == package_id
        ):
            fingerprints = target.get("sha256_cert_fingerprints", [])
            if any(
                isinstance(item, str)
                and item.replace(":", "").upper() == normalized_signer
                for item in fingerprints
            ):
                return True
    return False


def probe_android_device(
    device_id: str,
    adb: Optional[Path] = None,
) -> Dict[str, Any]:
    tool = adb or DEFAULT_ADB
    if tool is None or not tool.exists():
        located = shutil.which("adb")
        if not located:
            return {
                "device_id": device_id,
                "healthy": False,
                "error": "adb_unavailable",
            }
        tool = Path(located)
    completed = subprocess.run(
        [str(tool), "-s", device_id, "get-state"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    state = completed.stdout.strip()
    return {
        "device_id": device_id,
        "healthy": completed.returncode == 0 and state == "device",
        "state": state,
        "return_code": completed.returncode,
        "stderr": completed.stderr.strip(),
    }
