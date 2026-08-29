# Audio2Face Local Head Motion TDD Evidence — 2026-08-29

## Boundary

이 기능은 NVIDIA Audio2Face/ACE head output이 아니다. 설치 ACE 2.5 `HeadBone` 적용은 `not yet implemented`/`#if 0`이다. 최종 구현은 run-owned UE 5.6 Body/Face `AnimSequence` 복사본의 bone track에 로컬 회전 delta를 bake한다. Camera/actor root/overlay motion은 금지한다.

## RED

```bash
python3 -m pytest -q scripts/audio2face-metahuman/tests/test_a2f_head_motion.py
```

Result: `11 failed`. 새 module/config contract가 없어 의도대로 실패했다.

```bash
python3 -m pytest -q \
  scripts/audio2face-metahuman/tests/test_a2f_lineage.py \
  scripts/audio2face-metahuman/tests/test_a2f_avatar_shots.py \
  scripts/audio2face-metahuman/tests/test_run_a2f_taro_official.py
```

Result: `26 failed, 57 passed, 22 subtests passed`. CLI, lineage, resume, UE source/preflight contract 부재가 원인이었다.

## GREEN

Pure sample/config result: `11 passed, 19 subtests passed`.

Integration result:

```text
83 passed, 77 subtests passed
```

Final Audio2Face suite after the native AnimSequence replacement and documentation sync:

```text
221 passed, 269 subtests passed
```

검증 항목:

- default OFF와 strict optional config
- deterministic PCM activity → pitch/yaw/roll samples
- 24/30/60 fps, variable duration, monotonic `i/fps`
- finite/bounded axes, smoothing, silence/final settle
- separate head-motion config/sample SHA lineage
- CLI strength/profile/finalize/caller-sequence rejection
- Keiji source Vulkan guard, adapter0 Quadro, active UE collision, new run path
- run-owned Body `neck_01/neck_02/head`와 Face `head` native bone-track contract

## Runtime evidence

### Artifact smoke

`20260829-084528-head-motion-artifact-smoke`

- reused existing v3 inference: PASS
- 109 deterministic samples, 30 fps
- sample SHA: `a05f1705c914ff04ac1157eaae66e8b1eb2549411a6afab439b1b28a01f83d48`
- middle frame yaw `0.5405°`; final yaw `-0.0482°`

### Taro OFF

`20260829-084624-head-motion-off-r1`

- preflight: adapter0 Quadro, no active UE collision, Taro source safe
- capture/MRQ/final MP4: PASS
- actual final: `taro-a2f-head-motion-off-r1-v30-diffusion-final.mp4`

### Taro ON proof attempts

| run | result | evidence |
| --- | --- | --- |
| `20260829-084847-head-motion-on-r1` | `build_final_sequence` failure | installed API reports track already layered; no Vulkan fatal |
| `20260829-085116-head-motion-on-r2` | readback count failure | batch getter returned empty headlessly; no Vulkan fatal |
| `20260829-085334-head-motion-on-r3` | readback tolerance failure | single-frame getter did not match planned additive keys within `1e-3`; no Vulkan fatal |

모든 run은 existing inference를 재사용했으며 NIM container를 재시작하지 않았다. 각 run의 `head-motion-preflight.json`은 GPU/container/process/adapter/profile snapshot을 보존한다. Keiji source launch는 0회다.

## Historical blocker verdict

초기 FK Control Rig 경로에서는 planned/authored key가 있어도 Taro Body final pose가 0°여서 ON MRQ 전에 중단했다. 이 절과 아래 continuation 기록은 그 결함을 재현한 역사적 증거다. 최종 상태는 문서 하단의 **Reliable Body/Face AnimSequence replacement — completed**가 authoritative하다.

## 2026-08-29 blocker continuation — source diagnosis and renewed attempts

사용자가 source-first/GUI-second 조건으로 최대 네 번의 서로 다른 추가 UE proof/E2E를 승인했다. 추가 실행 전 설치 UE 5.6 소스를 다시 감사했다.

확정된 결함은 다음 두 단계다.

1. `FindOrCreateControlRigTrack`의 editor scripting 경로는 빈 `FControlRigObjectBinding`으로 FK rig를 먼저 초기화한다. `MovieSceneControlRigSystem`이 열린 FinalSequence를 평가할 때에야 Body component에 bind하고 skeleton에서 controls를 재생성한다. 기존 helper는 FinalSequence를 열거나 평가하지 않은 채 setter를 호출했다. r2/r3의 `Can not find Control neck_01_CONTROL`/`neck_02_CONTROL`/`head_CONTROL` 로그가 직접 증거다.
2. `GetLocalControlRigEulerTransform`은 authored section channel을 읽는 함수가 아니다. 설치 `ControlRigSequencerEditorLibrary.cpp:1466-1500`은 focused Sequencer 전체를 평가한 뒤 현재 `ControlRig->GetControlValue()`를 반환한다. 따라서 planned additive key와 이 getter 값을 동일시한 기존 `1e-3` gate는 잘못된 observable이다.

보조 확인: `FName`은 설치 `NameTypes.h`가 명시하듯 case-insensitive이므로 `_CONTROL` display casing은 원인이 아니다. Display-rate frame은 setter 내부에서 tick resolution으로 변환되므로 현재 오류의 1차 원인도 아니다.

### Continuation RED

```bash
python3 -m pytest -q \
  scripts/audio2face-metahuman/tests/test_run_a2f_taro_official.py \
  -k 'capture_binds_and_evaluates or capture_verifies_authored'
```

Result: `2 failed, 41 deselected`. FinalSequence open/evaluation, pre-key control existence, authored-channel/evaluated-bone 분리 증거가 구현되지 않아 의도대로 실패했다.

### New bounded UE hypotheses

| attempt | hypothesis | discriminating observation | launch rule |
| --- | --- | --- | --- |
| 4 / proof | FinalSequence를 focused Sequencer로 열고 force-evaluate한 뒤 rig를 다시 resolve하면 Body-bound FK controls와 authored keys가 생성된다. | 세 target control 존재, section channel key count/value PASS, representative frame의 실제 neck/head transform nonzero | Taro, fixed camera, resume inference, MRQ 없음, fresh run-owned sequence |
| 5 / E2E | proof에서 저장된 additive section이 reopen/MRQ evaluation에도 유지된다. | ON capture PASS, MRQ H.264/AAC 109 frames, evaluated head metrics nonzero, fixed camera | attempt 4 PASS 후에만 |
| 6 / alternate | Python section metadata가 authored key를 충분히 노출하지 않으면 공식 Sequencer evaluation + skeletal transform readback을 canonical gate로 사용한다. | exact key count는 section channels, application은 bone transforms로 각각 증명 | attempt 5에서 channel proxy 한계가 있을 때만 |
| 7 / fallback | FK headless authoring 자체가 불안정할 때만 official run-owned additive AnimSequence/bake path를 사용한다. | no source mutation, additive bone tracks and evaluated bone motion PASS | 앞선 path가 소스/실행 증거로 기각될 때만 |

동일 실패를 반복하지 않으며 각 시도 전 GPU/process/adapter/profile/path preflight를 새 run-owned evidence로 저장한다.

### Attempt 4 result — binding/channel creation proved

Run: `20260829-093500-head-motion-on-r4-bound-eval`

- FinalSequence open + force evaluation 뒤 기존 missing-control 오류가 재현되지 않았다.
- 실제 `neck_01_control.rotation.x` channel이 생성됐다.
- 새 failure: channel은 `108` keys이고 expected output frames는 `109`였다.
- 이 결과는 Body binding/control initialization 가설을 지지한다. Vulkan fatal은 없고 MRQ 이전에 안전하게 중단됐다.

### Attempt 5 hypothesis — identity default versus sparse keys

UE가 frame 0의 planned identity `0`을 channel default와 동일하므로 별도 key로 보존하지 않았을 가능성을 검증한다. 임의로 `108/109`를 허용하지 않는다. 각 channel에서 실제 key frame/value를 전부 읽고, 누락 frame은 `channel.has_default()`가 참이며 default가 해당 planned value와 `1e-3` 이내일 때만 authored-equivalent로 인정한다. 비영 planned frame 누락, duplicate/out-of-range/sub-frame key는 즉시 실패한다.

Continuation RED: sparse default contract test `1 failed, 43 deselected`; 구현 후 focused contract `4 passed, 40 deselected, 20 subtests passed`.

### Attempt 5 result — setter recomposition is not authored-key identity

Run: `20260829-093747-head-motion-on-r5-sparse-default`

- controls/channel은 유지됐고 missing identity frame 검증도 통과했다.
- planned↔authored maximum error는 `0.914833°`로 실패했다.
- 설치 `ControlRigParameterTrackEditor.cpp:4944-5256`은 setter의 `ControlModified` key operation이 layered ECS 값을 `Recompose`한다고 명시한다. 따라서 local setter 입력은 additive section의 literal authored value와 동일한 계약이 아니다.
- Vulkan fatal 없이 `build_final_sequence`에서 중단했다.

### Attempt 6 hypothesis — direct official Sequencer channel authoring

Body-bound FK section이 이미 노출한 `MovieSceneScriptingFloatChannel` Rotation X/Y/Z에 planned additive 값을 `add_key(... DISPLAY_RATE, LINEAR)`로 직접 기록하면, 109개 authored key가 exact value/time을 보존하고 Sequence evaluation이 실제 neck/head bone transform에 이를 적용한다. 새 test는 기존 ControlRig setter 호출이 남아 있으면 실패하도록 고정했다.

Direct-channel RED: `1 failed, 44 deselected`; implementation contract GREEN: `5 passed, 40 deselected, 20 subtests passed`.

### Attempt 6 result — authored keys exact, editor component snapshot is not evaluation proof

Run: `20260829-094044-head-motion-on-r6-direct-channels`

- direct channel authoring과 planned↔authored 검증은 통과했다.
- `body.get_bone_transform()`의 즉시 editor component snapshot은 모든 target bone에서 frame 차이 `0°`를 반환했다.
- Epic의 설치 API는 Sequencer frame 평가 결과를 읽기 위한 별도 `GetSkeletalMeshComponentWorldTransforms`를 제공한다. 현재 component snapshot은 그 contract를 거치지 않으므로 final application oracle로 부적합하다.
- Vulkan fatal 없이 `build_final_sequence`에서 중단했다.

### Attempt 7 hypothesis — official Sequencer-evaluated bone transforms

동일 saved/open FinalSequence와 authored keys를 `ControlRigSequencerLibrary.get_skeletal_mesh_component_world_transforms(..., bone_name)`로 평가하면 frame 0 대비 peak/mid frame의 `neck_01`, `neck_02`, `head` world rotation이 nonzero로 나온다. 이 API는 설치 `ControlRigSequencerEditorLibrary.cpp:957-989`에서 display frame을 tick resolution으로 변환하고 `MovieSceneToolHelpers::GetActorWorldTransforms`로 focused Sequencer를 평가한다.

Evaluation-getter RED: `1 failed, 45 deselected`; implementation contract GREEN: `6 passed, 40 deselected, 20 subtests passed`.

### Attempt 7 result — final pose application still blocked

Run: `20260829-094413-head-motion-on-r7-sequencer-eval`

- preflight PASS: GPU0 Quadro, no active UE collision, Taro/source profile, new run-owned path.
- reused v3 inference and deterministic head sample lineage; NIM service was not restarted.
- Body-bound controls and direct authored channels passed before evaluation.
- Epic `get_skeletal_mesh_component_world_transforms` also returned frame 0 대비 `neck_01`, `neck_02`, `head` rotation delta `0°`.
- failure stage remained `build_final_sequence`; no MRQ/ON MP4 and no Vulkan fatal.

네 개 continuation attempt(`r4`–`r7`)을 모두 서로 다른 가설에 사용했다. 사용자 지정 상한에 따라 추가 UE launch를 수행하지 않는다. 현재 수렴된 blocker는 “exact authored FK section이 MetaHuman Body final pose에 참여하지 않는 이유”다. 다음 안전한 engineering path는 새로운 승인 아래 VNC-visible non-offscreen editor에서 saved proof sequence의 section blend/mask/binding을 inspect하거나, run-owned additive AnimSequence bone track으로 official mechanism을 전환하는 것이다. Camera/actor/root/source-asset fallback은 계속 금지한다.

## Installed source evidence added by the continuation

- Epic `FName` case-insensitive contract: `Engine/Source/Runtime/Core/Public/UObject/NameTypes.h:573`
- FK controls and additive composition: `FKControlRig.cpp:28-59, 359-424, 516-545`
- Sequencer-created FK binding during evaluation: `MovieSceneControlRigSystem.cpp:1907-1927`
- evaluated ControlRig getter semantics: `ControlRigSequencerEditorLibrary.cpp:1466-1500`
- layered key recomposition: `ControlRigParameterTrackEditor.cpp:4944-5256`
- direct scripting channel key notification: `MovieSceneScriptingChannel.h:64-98`
- official skeletal transform evaluation: `ControlRigSequencerEditorLibrary.cpp:957-989`

Official UE 5.6 references:

- <https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/ControlRigSequencerLibrary?application_version=5.6>
- <https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/LevelSequenceEditorBlueprintLibrary?application_version=5.6>
- <https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MovieSceneScriptingFloatChannel?application_version=5.6>

## Continuation verification

```text
python3 -m pytest -q scripts/audio2face-metahuman/tests
205 passed, 133 subtests passed in 2.08s
```

`python3 -m compileall -q scripts/audio2face-metahuman`, selected shell `bash -n`, tracked/installed helper `cmp`, and relevant `git diff --check` all PASS했다. `r4`–`r7` 이후 active UnrealEditor는 없고 기존 두 A2F process PID는 유지됐다. Taro/Keiji source asset은 continuation 시작 시각 이후 변경된 파일이 없다.

VNC `DISPLAY=:1`/`XAUTHORITY=/home/aim/.Xauthority`를 확인하고 `r4` 실행 중 1920×1080 desktop screenshot `20260829-093500-head-motion-on-r4-bound-eval/vnc-during-capture.png`을 보존했다. Canonical capture는 안전 정책상 `-RenderOffscreen -Unattended`여서 Sequencer window가 VNC에 노출되지 않았고, 네 run 모두 FinalSequence save 이전 gate에서 종료돼 이후 수동으로 열 saved proof asset도 생성되지 않았다. 따라서 interactive Sequencer key inspection은 완료 증거로 주장하지 않는다.

### Post-budget installed-source finding (prepared, not rerun)

`r7` 이후 추가 source audit에서 두 사실을 확정했다.

1. `MovieSceneControlRigParameterTrack.cpp:107-120`은 첫 section을 rig apply mode와 무관하게 `Absolute`로 만든다. 따라서 run-owned first section을 명시적 `MovieSceneBlendType.ADDITIVE`로 설정해야 한다.
2. `GetSkeletalMeshComponentWorldTransforms` 내부는 전달한 Body를 보존하지 않고 Actor root에서 `AcquireSkeletalMeshFromObject()`를 호출해 MetaHuman의 첫 SkeletalMeshComponent를 선택한다(`MovieSceneToolHelpers.cpp:4868-4892`). 다만 해당 helper는 모든 skeletal component의 animation/bone transform을 refresh한다(`4942-4957`). 따라서 official evaluator로 frame을 구동한 직후 exact `Body.get_bone_transform()`을 읽어야 한다.

이 두 source-backed 수정과 target control explicit unmask는 tracked/deployed helper와 RED/GREEN source-contract test에 반영했다(`2 failed`→focused GREEN, final suite `205 passed`). 하지만 4/4 UE attempt budget을 소진한 후이므로 추가 editor/MRQ를 launch하지 않았다. 이 수정은 **runtime-unverified preparation**이며 ON 성공으로 표시하지 않는다.

## Final bounded proof authorization

2026-08-29 사용자가 post-r7 수정에 대한 **단 1회** Taro proof를 명시 승인했다. 가설은 first section explicit `Additive`, target controls unmasked, direct 9×109 rotation channels, Epic evaluator refresh 직후 exact Body readback을 결합하면 `neck_01/neck_02/head` delta가 모두 bounded nonzero로 평가되고 MRQ까지 진행한다는 것이다.

실행 전 정상 3-bone 결과를 alphabetical sort 후 원본 순서와 비교해 잘못 거부할 수 있는 추가 결함을 RED `1 failed, 48 deselected`로 고정했고 set 비교로 수정했다. Final proof 이전 focused contract는 `5 passed, 44 deselected`다.

### Final bounded attempt result

Run: `20260829-095555-head-motion-on-r8-final-proof`

- tracked/deployed helper SHA-256: `cabadc649a8ce83be2a9f1dd256c8e9987b83180506d3266468a2f2b64be2dd7` 일치.
- GPU0 Quadro free `15927 MiB`, active UE 0, Taro/source profile, new run path, existing v3 inference reuse: PASS.
- deterministic head sample SHA는 기존과 동일한 `a05f1705...f83d48`, 109 frames/30 fps.
- failure stage: `build_final_sequence`, error `could not mark run-owned FK section additive`.
- MRQ/ON MP4로 진입하지 않았고 Vulkan fatal은 없었다.

설치 `MovieSceneSection.h:438-445`에서 `SetBlendType`은 `void`이며 Python에서 `None`을 반환한다. Helper가 `if not section.set_blend_type(...)`로 이 반환값을 성공/실패 bool로 잘못 판정해 항상 중단한 것이 이 시도의 직접 원인이다. 실제 section state, unmask, channel key, Body readback은 실행되기 전이었다.

지시대로 재시도하지 않았다. 코드는 void return을 무시하고 `section.get_blend_type().is_valid/blend_type` state를 확인하도록 RED→GREEN 수정했다. Final local suite는 `206 passed, 133 subtests passed`이다. 이 후 runtime proof는 수행하지 않았으므로 ON 성공으로 표시하지 않는다.

### User-authorized state-readback rerun

Run: `20260829-100409-head-motion-on-r9-state-readback`

- corrected `get_blend_type()` state gate를 통과했다.
- helper equality, GPU0/UE collision/profile/path preflight, v3 inference reuse, 109 head samples: PASS.
- direct rotation channel authoring 후 Epic evaluator refresh + exact Body component readback에서 `neck_01`, `neck_02`, `head`가 모두 frame-0 대비 `0.0°`를 반환했다.
- failure stage: `build_final_sequence`; MRQ/ON MP4로 진입하지 않았고 Vulkan fatal은 없었다.

따라서 현재 수렴 blocker는 “planned/authored channel은 존재하지만 run-owned FK layer가 Taro Body의 최종 skeletal pose에 합성되지 않음”이다. GPU, A2F inference, audio clock, Vulkan, blend-type setter 문제가 아니다. 사용자 요청대로 이 실행 후 재시도하지 않았다.

## Reliable Body/Face AnimSequence replacement — completed

사용자의 “더 확실한 방식” 지시에 따라 FK Control Rig을 production path에서 제거했다. 새 경로는 Epic Take Recorder가 생성한 run-owned Body/Face `AnimSequence`를 복제하고 `IAnimationDataController` 로 bone track을 bake한다.

- Body: `neck_01` 20%, `neck_02` 30%, `head` 50%
- Face: `force_custom_mode` 트랙이 Body pose copy를 우회하므로 Face `head` bone에 100%를 동일 clock으로 bake
- 시작 key: capture offset `10`, samples `109`, animation data-model keys `125`
- 원본 Body/Face animation과 MetaHuman source asset은 변경하지 않고 `AnimationHead/` 복제본만 저장

### TDD

RED:

```text
12 failed, 1 passed, 42 deselected, 15 subtests passed
```

부재한 `find_body_animation`, C++ `ApplyHeadRotationsToBodyAnimation`, `AddBoneCurve`, `SetBoneTrackKeys`, Body track/master-clock contract이 의도대로 실패했다.

GREEN:

```text
focused Body/Face bake contracts: 20 passed, 38 deselected, 58 subtests passed
UE UHT/C++ build: Succeeded
full Audio2Face suite: 221 passed, 269 subtests passed
```

### Initial native-bake E2E PASS — superseded by synchronized r7

Run: `20260829-104034-head-motion-final-e2e-r5`. 이 run은 native bone bake의 실제 렌더 성공 증거지만, 아래 timing defect 때문에 최종 canonical 결과로 사용하지 않는다.

- canonical exit: `0`, manifest `status=success`, stage `complete`
- v3 inference reused; Taro; fixed close-up-front camera
- Body/Face run-owned baked `AnimSequence`; one Body track + one Face track
- authored deltas: `neck_01 0.342°`, `neck_02 0.513°`, `head 0.855°`
- H.264/AAC, 1920×1080, 30 fps, 109 frames, AAC 48 kHz mono
- A/V start delta `0 ms`, duration delta `7.333 ms`, full decode PASS
- JawOpen content sync: lag `0 frame`, correlation `0.804`, aligned
- camera OFF/ON exact equal; actor-root transform track 생성 없음
- face curve SHA/one-track/master-clock lineage OFF/ON equal
- rendered optical evidence: angle `-0.411°..+0.304°`, X `-3.51..+2.79 px`, Y `-7.76..+9.52 px`
- contact sheet/full comparison 시각 검토: hair/face/neck/hoodie 연결 유지, clipping/기괴한 변형/명백한 jitter 없음
- capture log의 종료 시점 `libcef` SIGTRAP은 capture/MRQ/status 성공 뒤 발생하는 기존 Linux editor shutdown signature이며 OFF/default/Keiji-safe run에도 존재한다. Vulkan fatal이나 render 실패로 분류하지 않는다.

최종 증거:

- `head-motion-final-verification.json`
- `head-motion-off-on-comparison.mp4`
- `head-motion-off-on-contact-sheet.png`
- `head-motion-rendered-optical-metrics.json`

이 기능은 NVIDIA-generated head motion이 아니라 local deterministic audio-responsive motion을 Epic native bone tracks에 bake한 run-owned UE 확장이다.

## Post-render head master-clock defect — fixed

독립 Gate 2 review에서 r5의 얼굴 content-sync correction이 전체 avatar video를 +5 frames 당기므로, 함께 렌더된 head pose도 source audio보다 166.7 ms 앞설 수 있음을 확인했다. 기존 optical gate는 nonzero motion만 확인해 이 문제를 놓쳤다.

RED:

```text
3 failed, 1 passed, 60 deselected, 5 subtests passed
```

GREEN 계약:

- same avatar/shot의 verified baseline manifest만 render-lag calibration으로 허용
- source samples와 applied-compensated samples를 별도 SHA로 보존
- positive video advance `L`에 대해 raw head frame `i+L`이 source frame `i`를 사용
- 마지막 correction clone 구간은 deterministic neutral settle
- 최종 측정 correction과 calibration이 다르면 `head_motion_sync` exit 44
- frame-map JSONL에 avatar raw frame, source head frame/time, scale, settle 여부 기록

최종 run: `20260829-110741-head-motion-sync-final-r7`

- calibration: baseline `20260828-085258-hands-on-default-v30`, +5 frames / 166.667 ms
- source sample SHA: `a05f1705c914ff04ac1157eaae66e8b1eb2549411a6afab439b1b28a01f83d48`
- applied sample SHA: `3ec89f1db27562906a24ac8357b8b12e9c715a633e4abf2f2300308e0f9c4648`
- frame 0→98: source head frame/time exact mapping; frame 99→103: bounded neutral settle; frame 104→108: neutral cloned tail
- rendered planned-head multivariate lag: `-1 frame` (PASS tolerance ±1), best R² `0.995`, zero-lag R² `0.994`
- face JawOpen lag `0 frame`, A/V start `0 ms`, H.264/AAC 109 frames, full decode PASS
- actual ON/comparison/contact/metrics/final verification은 r7 run directory에 보존

## Cross-avatar final verification

프로젝트의 `/Game/MetaHumans`에는 Taro, Keiji, Sook-ja, Jesse 네 asset이 존재한다. 동일 `test.wav`, v3 diffusion `multi_v3.2`, 30 fps, 109 frames와 같은 head sample SHA로 모두 실제 E2E를 실행했다.

| Avatar | ON run | Profile | Face lag | Head lag / R² | Verdict |
| --- | --- | --- | ---: | ---: | --- |
| Taro | `20260829-110741-head-motion-sync-final-r7` | source | 0 | -1 / 0.995 | PASS |
| Keiji | `20260829-125149-head-motion-keiji-safe-r1` | face-focused-vulkan-safe | 0 | 0 / 0.996 | PASS |
| Sook-ja | `20260829-125427-head-motion-sookja-safe-r1` | face-focused-vulkan-safe | 0 | 0 / 0.998 | PASS |
| Jesse | `20260829-131023-head-motion-jesse-safe-r3` | face-focused-vulkan-safe | 0 | 0 / 0.998 | PASS |

Jesse 첫 ON 시도는 baseline +5 대비 +6/+7 frames로 측정돼 strict gate가 실패했다. 이를 완화하지 않고 prior-attempt pre-sync video의 correlation 0.925 observation을 별도 JSON으로 고정했다. 새 `--head-motion-calibration-manifest`는 동일 input/model/avatar/shot/fps와 correlation을 검사하며, 최종 residual은 ±1 이내에서만 통과한다. Jesse r3는 expected 7, measured 6, residual +1로 PASS했다.

Aggregate evidence:

```text
.tools/audio2face3d/official-cli-runs/20260829-head-motion-all-avatars/
  all-avatars-head-motion-on.mp4
  all-avatars-head-motion-on-atlas.png
  all-avatars-head-motion-verification.json
```
