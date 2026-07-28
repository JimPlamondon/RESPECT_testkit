# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from types import SimpleNamespace

import respect_compat.android_apk as android_apk
from respect_compat.android_apk import (
    assetlinks_matches,
    parse_manifest_xml,
    probe_android_device,
)


def test_android_manifest_parser_finds_app_link_and_xapi_query():
    manifest = """\
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="org.example.canapp">
  <queries>
    <intent>
      <action android:name="org.openeel.action.xapioveripc" />
    </intent>
  </queries>
  <application>
    <service android:name=".RuntimeDriverService" android:exported="true">
      <intent-filter>
        <action android:name="org.openeel.action.xapioveripc" />
      </intent-filter>
    </service>
    <activity android:name=".MainActivity" android:exported="true">
      <intent-filter android:autoVerify="true">
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data android:scheme="https" android:host="canapp.example" />
      </intent-filter>
    </activity>
  </application>
</manifest>
"""
    result = parse_manifest_xml(manifest)
    assert result["package_id"] == "org.example.canapp"
    assert result["app_links"] == [
        {
            "activity": ".MainActivity",
            "exported": True,
            "scheme": "https",
            "host": "canapp.example",
            "auto_verify": True,
        }
    ]
    assert result["query_actions"] == ["org.openeel.action.xapioveripc"]
    assert result["services"] == [
        {
            "service": ".RuntimeDriverService",
            "exported": True,
            "actions": ["org.openeel.action.xapioveripc"],
        }
    ]


def test_android_device_probe_reports_missing_adb_without_claiming_health(tmp_path):
    result = probe_android_device("emulator-5554", adb=tmp_path / "missing-adb")
    assert not result["healthy"]
    assert result["device_id"] == "emulator-5554"


def test_android_device_probe_records_attributable_environment(tmp_path, monkeypatch):
    adb = tmp_path / "adb"
    adb.write_bytes(b"test")
    responses = iter(
        [
            SimpleNamespace(
                returncode=0,
                stdout="device\n",
                stderr="",
            ),
            SimpleNamespace(
                returncode=0,
                stdout=(
                    "[ro.kernel.qemu]: [1]\n"
                    "[ro.product.manufacturer]: [Google]\n"
                    "[ro.product.model]: [sdk_gphone64_arm64]\n"
                    "[ro.build.version.release]: [15]\n"
                    "[ro.build.version.sdk]: [35]\n"
                    "[ro.build.fingerprint]: [google/sdk/example]\n"
                ),
                stderr="",
            ),
        ]
    )
    monkeypatch.setattr(
        android_apk.subprocess,
        "run",
        lambda *_args, **_kwargs: next(responses),
    )

    result = probe_android_device("emulator-5554", adb=adb)

    assert result["healthy"]
    assert result["emulator"] is True
    assert result["manufacturer"] == "Google"
    assert result["model"] == "sdk_gphone64_arm64"
    assert result["os_release"] == "15"
    assert result["api_level"] == "35"
    assert result["build_fingerprint"] == "google/sdk/example"


def test_assetlinks_match_requires_package_relation_and_signer():
    statements = [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": "org.example.canapp",
                "sha256_cert_fingerprints": ["AA:BB:CC"],
            },
        }
    ]
    assert assetlinks_matches(statements, "org.example.canapp", "AABBCC")
    assert not assetlinks_matches(statements, "org.example.other", "AABBCC")
    assert not assetlinks_matches(statements, "org.example.canapp", "DDEEFF")
