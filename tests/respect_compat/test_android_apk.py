# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

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


def test_android_device_probe_reports_missing_adb_without_claiming_health(tmp_path):
    result = probe_android_device("emulator-5554", adb=tmp_path / "missing-adb")
    assert not result["healthy"]
    assert result["device_id"] == "emulator-5554"


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
