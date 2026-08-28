# Audio2Face 멀티 아바타·멀티 shot TDD/검증 기록

## 범위

기존 무옵션 Taro 단일 영상 경로를 유지하면서 다음을 추가했다.

- MetaHuman 이름 또는 `/Game/...` Blueprint asset path 선택
- 공식 Epic import가 필요한 수동 경계와 hash 검증 resume
- 네 개 named shot과 strict custom camera JSON
- 한 번의 A2F capture를 여러 LevelSequence/MRQ render가 재사용
- manifest v2와 shot별 H.264/AAC 검증

## 공식 기준선

- NVIDIA ACE 2.5: `UACEBlueprintLibrary::AnimateCharacterFromWavFile`
- UE 5.6: `TakeRecorderSubsystem.set_target_sequence`, `add_source_for_actor`, `start_recording`, `stop_recording`, 완료 delegate
- UE 5.6 SequencerScripting 예제: `add_spawnable_from_instance`, `MovieScene3DTransformTrack`, Camera Cut
- UE 5.6 MRQ: `MoviePipelinePythonHostExecutor` + `ExecutorPythonClass`
- Epic MetaHuman/Fab: 계정 로그인, 라이선스 승인, Add to Project/Creator assembly는 사용자 UI 경계

URL과 설치 버전은 `docs/audio2face-taro-cli-pipeline.ko.md` 및 각 run `manifest.json`에 기록했다.

## RED → GREEN

| 단계 | RED 증거 | GREEN/회귀 증거 |
| --- | --- | --- |
| avatar/shot API | helper module 없음, parser에 `--avatar` 없음 | name/path, missing/ambiguous, preset/custom, resume, manifest tests PASS |
| run-owned map | `duplicate_asset` 뒤 같은 World를 다시 load하여 `EditorServer.cpp:2516`, signal 11 | 공식 `EditorLoadingAndSavingUtils.save_map` 후 run map load; source SHA 전/후 동일 |
| setup 재진입 | `save_map` 내부 Slate pump 중 setup tick 재진입 | setup 전에 `phase=prepare_avatar_world`; static regression test PASS |
| custom rotation | positional `unreal.Rotator`로 `[pitch,yaw,roll]` 축이 바뀌어 배경-only 영상 생성 | keyword `pitch/yaw/roll`; resolved `[3.8,-90,0]`, 얼굴 프레임과 MP4 검증 PASS |
| secret forwarding | child가 전체 `os.environ`을 상속 | GUI/GPU/library allowlist만 전달, auth-agent/token 제외 test PASS, token pattern scan 0 |
| resume fidelity | 누락 avatar 안내가 shot request를 잃음 | shell-quoted resume command가 named/custom shot과 config/map을 보존 |
| Unreal option injection | `--map=-ExecCmds=...`가 engine argv로 전달 가능 | `/Game/...` package/object reference whitelist를 command builder와 main에 적용 |
| timeout descendants | MRQ direct child timeout만 처리 | capture/MRQ 모두 새 process group과 TERM→KILL→reap 적용 |
| malformed JSON types | list preset/coordinate space가 raw `TypeError` | 모든 타입을 `ShotConfigError`로 정규화하여 exit 48 보장 |

잘못 생성된 custom 배경-only run은 진단 증거로만 보존하며 성공 결과로 사용하지 않는다.

```text
.tools/audio2face3d/official-cli-runs/20260826-233340-avatar-feature-custom-shots/
```

## 자동 테스트

```bash
python3 -m pytest -q \
  scripts/audio2face-metahuman/tests/test_a2f_avatar_shots.py \
  scripts/audio2face-metahuman/tests/test_run_a2f_taro_official.py \
  scripts/audio2face-metahuman/tests/test_run_a2f_taro_cli.py
```

결과: `39 passed`.

순수 입력 계약 모듈 coverage:

```bash
python3 -m coverage run -m pytest -q \
  scripts/audio2face-metahuman/tests/test_a2f_avatar_shots.py
python3 -m coverage report -m --include='*/a2f_avatar_shots.py'
```

결과: `a2f_avatar_shots.py` 89%.

## 실제 E2E gate

| Run | 결과 |
| --- | --- |
| `20260827-095728-test-wav-visible-a2f-final` | 정상 package map, 단일 track, 실제 입 벌림/치아 노출, H.264/AAC PASS |
| `20260827-100106-test-wav-four-visible-final` | 네 preset 모두 단일 track·실제 발화·codec/audio/A/V/decode PASS |
| `20260827-100621-test-wav-custom-visible-final` | custom transform에서 실제 발화·codec/audio/A/V/decode PASS |
| `20260827-000315-gate2-final-missing` | 공식 import 수동 경계와 shot 보존 resume, exit 45 PASS |
| `20260827-000412-gate2-final-jesse` | exact path/skeleton readiness/source 격리 PASS, Vulkan PIE crash로 최종 E2E BLOCKED |
| `20260826-235435`, `235625`, `20260827-000057`, `001113` | codec/audio는 PASS였지만 얼굴 neutral. 잘못된 map self-reference 원인으로 성공 증거에서 폐기 |

성공 MP4 공통 gate:

- H.264 video + AAC audio stream
- 1920×1080, 30 fps, 120 contiguous frames, 4.000 s
- AAC 48 kHz mono, non-silent
- A/V start/duration delta 0 ms
- full video+audio decode PASS
- sampled frame hashes 3/3 unique
- 대표 프레임 시각 검토

## 남은 제한

- Epic/Fab/MetaHuman Creator 인증·라이선스·최초 import는 공식 UI에서 사용자가 수행한다.
- 현재 로컬 BP_Jesse는 UE 5.6 Linux Vulkan pipeline 생성 오류 때문에 MP4까지 도달하지 못한다. 자동 driver 변경, 원본 material 변경, 비공식 avatar/model 대체는 하지 않는다.
