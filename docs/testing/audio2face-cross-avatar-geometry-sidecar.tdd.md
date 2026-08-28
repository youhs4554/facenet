# Audio2Face Cross-Avatar / Geometry SDK Sidecar TDD

## Scope and gate order

This feature is intentionally gated:

1. acquire and import one elderly Asian male and one elderly Asian female MetaHuman;
2. run the same v3 curve lineage on Taro and both new MetaHumans;
3. only after the cross-avatar gate passes, build and run the isolated geometry SDK sidecar.

Phase B is not allowed to start while Phase A is incomplete or requires user action.

## TDD evidence

| Guarantee | RED | GREEN | Result |
|---|---|---|---|
| Only a Free official Fab listing with explicit `Asian`, `MetaHuman`, and `Editable` metadata is accepted | `python3 -m unittest scripts/audio2face-metahuman/tests/test_a2f_cross_avatar.py` failed because `a2f_cross_avatar.py` did not exist | Same command: 5 tests passed | PASS |
| Paid, missing-tag, non-MetaHuman, non-Standard, or training-use candidates are rejected | Same RED run | `test_paid_missing_metadata_or_training_use_is_rejected` | PASS |
| Login/MFA/EULA/account confirmation always blocks Phase B | Same RED run | `test_manual_boundary_never_allows_phase_b` | PASS |
| Taro and the candidate must use identical input/audio/model/NIM/curve/timeline lineage and distinct source assets | Same RED run | Two cross-avatar lineage tests passed | PASS |
| Taro acquisition is classified from artifacts and historical command evidence rather than memory | Missing classifier methods produced RED `AttributeError` | `test_taro_route_is_bridge_preassembled_but_not_policy_reusable` | PASS |
| Both elderly Asian gender slots require explicit official metadata and distinct IDs | Missing matrix methods produced RED `AttributeError` | Three role/matrix tests passed | PASS |
| One successful avatar never unlocks Phase B | Missing gate method produced RED `AttributeError` | `test_phase_a_is_partial_until_both_e2e_results_pass` | PASS |
| User-authorized visual selection is explicit, official-Bridge-only, SHA-backed, and never relabeled as demographic metadata | New Keiji/Sook-ja matrix errored with `explicit demographic metadata is required` | Two visual-provenance tests pass and emit `visual_estimate_not_demographic_metadata` | PASS |

Focused coverage after the two-avatar matrix extension is 82% (`159` statements, `29` missed). Full Audio2Face discovery reports `130` tests passed; Python compile also passes. Existing ResourceWarnings from older motion tests remain non-fatal and were not changed by this work.

## Taro provenance correction

The exact historical route is `A_bridge_preassembled`, but it was not a normal Bridge UI Download/Add operation. The earlier agent read an existing Bridge credential file, called the official MHC preset download API through curl, downloaded a Cinematic preassembled zip, and imported it with `unzip -n`.

This explains why no new account confirmation appeared for Taro, but that credential-reading route is forbidden now. The public 66-preset response contains no ethnicity, gender, or age fields; the old Taro candidate montage was based on names/previews and does not satisfy the new metadata contract.

Machine-readable evidence:

- `.tools/audio2face3d/cross-avatar-phase-a/20260827-taro-route-two-avatar-audit/taro-acquisition-provenance.json`
- `.tools/audio2face3d/cross-avatar-phase-a/20260827-taro-route-two-avatar-audit/elderly-asian-two-avatar-candidate-audit.json`

## Two-avatar catalog result

- exact elderly Asian male metadata candidate: Louis; rejected because paid and `.mhpkg` assembly path;
- exact elderly Asian female metadata candidate: Realistic aged female characters; rejected because paid;
- free Kabir/Advika/Seo near candidates: rejected because official age metadata is absent;
- free `EDO_CITIZEN_X`: has Unreal Engine + MetaHuman formats and a preassembled presentation, but its official listing contains neither `Asian` nor `old/elderly` metadata (both full-page searches returned 0/0);
- same Bridge preset collection: rejected for selection because all three demographic fields are absent.

The user later authorized visual assessment because the official catalog has no demographic fields. Review of all 66 official preset previews selected Keiji (`k8ezkISA`) and Sook-ja (`l01pkISw`). This is an appearance estimate, not official demographic metadata. Contact sheets and exact preview hashes are stored with the audit.

An isolated UE 5.6 project successfully loaded the official Bridge catalog without reading credentials. Bridge then required a new Epic Content License Agreement acceptance before enabling Unreal Unlimited. No acceptance or download was submitted. Phase A is `manual_action_required` before import/E2E and Phase B has not started.

The proposed AI-photo path was also checked against Epic's current workflow and local files. It requires a textured 3D head mesh, MetaHuman Identity solve, UE 5.6 Conform from Identity, and assembly. The installed Linux build marks the required Identity/face solver/MetaHuman Character editor and assembly pipeline modules Win64-only, so the workflow must be completed on Windows before migrating an assembled asset here.

## Official Fab UI result

The Seo listing was verified in the official Fab web UI on the VNC desktop:

- `Asian`, `MetaHuman`, and `Editable` tags are visible;
- included format is MetaHuman;
- compatibility is UE 5.6-5.8;
- file is `mhc_seo.mhpkg`, displayed size 143.52 MB;
- Fab Standard License and NoAI metadata are visible;
- Personal is Free only under the displayed revenue/funding condition;
- Professional is paid.

Opening My Library redirected to Epic's `Confirm Your Account` page. No button was clicked, no license tier was selected, and no acquisition was submitted. Evidence and the exact user step are recorded in:

`/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/cross-avatar-phase-a/20260827-seo-acquisition-gate/phase-a-manual-action.json`

## Current result

- Phase A: `pass`
- Required new avatars present in project: two of two (`Keiji`, `Sook-ja`)
- Both same-lineage v3 E2E runs: PASS
- Shared effective curve SHA: `8c7e24f2aed21c13ae6394f812072b3f255c62e76ea54896b00699d12a44f6b3`
- Phase B image build/inspect: PASS
- Phase B official build-option/engine-lineage/host-failure audit regression: PASS (18 focused tests)
- Phase B runtime: PASS after authorized bounded diffusion-NIM stop; direct skin/tongue/jaw/eyes and 68 solver weights exported
- Selected official preset candidates remain visual-estimate provenance, not Epic demographic metadata
- Existing Taro/Jesse assets and NIM containers: preserved

## Final Phase B result

- only `audio2face-3d-diffusion` was temporarily stopped; pretrained NIM remained running;
- diffusion was restored with the same container identity and endpoint 52100 `ONLINE`;
- FP32 official-default and explicit NIM-match FP16/GPU-solver runs are preserved separately;
- direct geometry visualization, PLY, raw tensors, timestamp CSV, comparison JSON and host restoration evidence are complete;
- no host CUDA/TensorRT/driver/global path changed.
