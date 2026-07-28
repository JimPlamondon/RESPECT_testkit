# Migration Provenance

The RESPECT testkit was extracted without history rewriting from [JiMS pull request 50](https://github.com/JimPlamondon/jims/pull/50) at merge commit `eccf623b1978ddcd50ef16b0353193fbf2152ede`. Complete pre-extraction history remains in `JimPlamondon/jims`.

## Authoring commits

- `0658140c5b33a30ce2747c4f4742c87b9880513c` — RESPECT Compatible Test Suite v0.1 harness.
- `438e10b7fe028e73b444592d293f1c6fa5bad856` — canonical Matrix merge.
- `1025e89011d42e75111ef9d541110f5a516bd4af` — Matrix-driven Test Suite.
- `4361643cb27e4710d21c87673ef4fa4dcd23d102` — RESPECT-ification Kit.

## Source lock

- Inventory: `migration/source_inventory.json`; SHA-256 (Secure Hash Algorithm 256-bit) aggregate `b2b61c31421dd6591fc48a1fd1d21de78f243c52f834d7a5045fccfea6565e50`.
- Manifest: `migration/source_manifest.json`; SHA-256 aggregate `2f03a77f2c933d4567d1e7d313a5af11912e7e0cb284ca23ffb44f4f41231ade`.
- Canonical Matrix: `respect-compatibility-matrix-v0.1` version `1.0.0`; semantic hash `c10090db5b2112a1fe5bfa39a13ca86aecca1d36d98f37ebe86592a6a196812c`; 43 features; 84 atomic rows; 21 mutation checks.
- Historical profile: `src/respect_compat/data/profiles/compatibility_matrix_v0_1.json`, preserved byte-for-byte as a distinct non-canonical runtime profile.
- OPDS revision: `8fda670fc72f110abcf68ad5d26e99ecfeeabf03`.
- Readium Web Publication Manifest revision: `655ee4bcea7f63e1226f166f6b128d9bea6c655b`.

## Inert historical locators

The following strings are byte-preserved source or provenance evidence. Runtime code does not resolve or dereference them.

| Artifact | JSON pointer | Preserved value |
|---|---|---|
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/0/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/app_links_validator.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/0/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/0/implementation_sources/1/locator` | `licensing-public/schemas/respect_compat/compatibility_matrix_v0_1.json` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/5/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/http_cache_validator.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/5/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/5/implementation_sources/1/locator` | `licensing-public/schemas/respect_compat/compatibility_matrix_v0_1.json` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/6/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/fake_launcher.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/6/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/8/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/8/implementation_sources/3/locator` | `licensing-public/harness/respect_compat/fake_launcher.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/12/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/android_metadata_validator.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/12/current_suite_mapping/harness_paths/1` | `licensing-public/harness/respect_compat/fake_launcher.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/12/current_suite_mapping/harness_paths/2` | `licensing-public/harness/respect_compat/http_cache_validator.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/12/current_suite_mapping/harness_paths/3` | `licensing-public/harness/respect_compat/manifest_validator.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/13/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/manifest_validator.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/19/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/http_cache_validator.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/19/current_suite_mapping/harness_paths/1` | `licensing-public/harness/respect_compat/opds_validator.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/19/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/19/implementation_sources/1/locator` | `licensing-public/schemas/respect_compat/compatibility_matrix_v0_1.json` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/20/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/20/nonimplementation_evidence/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/23/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/report.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/23/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/24/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/fake_launcher.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/24/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/24/implementation_sources/3/locator` | `licensing-public/harness/respect_compat/fake_launcher.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/25/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/tests/test_respect_compat.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/25/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/25/implementation_sources/1/locator` | `licensing-public/harness/respect_compat/tests/test_respect_compat.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/26/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/report.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/26/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/26/implementation_sources/1/locator` | `licensing-public/schemas/respect_compat/compatibility_matrix_v0_1.json` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/26/implementation_sources/2/locator` | `licensing-public/harness/respect_compat/cli.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/27/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/cli.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/27/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/27/implementation_sources/1/locator` | `licensing-public/harness/respect_compat/cli.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/28/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/models.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/28/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/28/implementation_sources/1/locator` | `licensing-public/harness/respect_compat/cli.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/29/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/fake_lrs.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/29/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/29/implementation_sources/3/locator` | `licensing-public/harness/respect_compat/fake_lrs.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/32/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/fake_lrs.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/32/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/32/implementation_sources/2/locator` | `licensing-public/harness/respect_compat/fake_lrs.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/33/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/fake_lrs.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/33/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/37/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/fake_lrs.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/37/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/38/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/39/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/fake_lrs.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/39/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/41/current_suite_mapping/harness_paths/0` | `licensing-public/harness/respect_compat/fake_lrs.py` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/42/implementation_sources/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/features/42/nonimplementation_evidence/0/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/source_locks/1/local_path` | `/Users/jim/Developer/JiMS/Temp/respect-code-inspect/RESPECT-Consumer-App-Integration-Guide` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/source_locks/2/local_path` | `/Users/jim/Developer/JiMS/Temp/demolaunchableapp-upstream-audit` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/source_locks/3/local_path` | `/Users/jim/Developer/JiMS/Plans/Research/RESPECT_Level5_Matrix/20260727_direct_evidence_reuse/compatibility_matrix.json` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/source_locks/4/local_path` | `/Users/jim/Developer/JiMS/Temp/complete-respect-compatibility-matrix` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/source_locks/5/local_path` | `/Users/jim/Developer/JiMS/Temp/respect-web-compat-slice` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/source_locks/8/local_path` | `/Users/jim/Developer/JiMS/Temp/respect-requirements-audit` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/source_locks/9/local_path` | `/Users/jim/Developer/JiMS/Temp/respect-upstream-audit` |
| `src/respect_compat/data/matrix/compatibility_matrix.json` | `/source_locks/10/local_path` | `/Users/jim/Developer/JiMS/Temp/respect-upstream-audit` |
| `src/respect_compat/data/indexes/source_interaction_index.json` | `/evidence_items/1/locator` | `/Users/jim/Developer/JiMS/Plans/RESPECT_Test_Suite_Level_5/01_Current_State_and_RESPECT_Interaction_Audit.md` |
| `src/respect_compat/data/indexes/source_interaction_index.json` | `/evidence_items/5/locator` | `/Users/jim/Developer/JiMS/Plans/Research/RESPECT_Level5_Matrix/20260727_direct_evidence_reuse/compatibility_matrix.json` |
| `src/respect_compat/data/indexes/source_interaction_index.json` | `/evidence_items/10/locator` | `licensing-public/harness/respect_compat/web_target.py and tests at f885585aabf0c0d224db41136b8a337c358a8b18` |
| `src/respect_compat/data/indexes/source_interaction_index.json` | `/evidence_items/11/locator` | `licensing-public/schemas/respect_compat/compatibility_matrix_v0_1.json` |
| `src/respect_compat/data/indexes/source_interaction_index.json` | `/evidence_items/58/locator` | `licensing-public/harness/respect_compat/cli.py` |
| `src/respect_compat/data/indexes/source_interaction_index.json` | `/evidence_items/59/locator` | `licensing-public/harness/respect_compat/cli.py; fake_launcher.py; fake_lrs.py; tests/test_respect_compat.py; licensing-public/schemas/respect_compat/compatibility_matrix_v0_1.json` |
| `src/respect_compat/data/indexes/source_interaction_index.json` | `/evidence_items/60/locator` | `licensing-public/harness/respect_compat/fake_launcher.py` |
| `src/respect_compat/data/indexes/source_interaction_index.json` | `/evidence_items/61/locator` | `licensing-public/harness/respect_compat/fake_lrs.py` |
| `src/respect_compat/data/indexes/source_interaction_index.json` | `/evidence_items/62/locator` | `licensing-public/harness/respect_compat/tests/test_respect_compat.py` |
