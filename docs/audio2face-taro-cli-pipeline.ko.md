# Audio2Face-3D → UE 5.6 MetaHuman 멀티 아바타·멀티 카메라 CLI

> 사용자용 범용 명령과 최신 control/progress/clean mannequin 설명은 [Audio2Face-3D → 범용 MetaHuman CLI 사용 설명서](audio2face-metahuman-cli.ko.md)를 사용한다. 이 문서는 초기 Taro 기반 구현과 과거 검증 기록을 보존한다.

## 결론

임의 오디오 입력에서 NVIDIA Audio2Face-3D NIM, NVIDIA ACE Unreal Plugin, UE 5.6 Take Recorder, Epic Movie Render Queue, 프로젝트 FFmpeg를 거쳐 H.264/AAC MP4를 만드는 단일 CLI를 구현했다. 기본값은 기존과 동일한 Taro 정면 단일 영상이며, 로컬 MetaHuman 이름/asset path와 여러 카메라 구도를 선택할 수 있다.

2026-08-27 제품 기본값 변경 이후 canonical no-option 모델은 `v3.0-diffusion`/`multi_v3.2`/52100이다. `v2.3-regression`/52000은 `--a2f-model v2.3-regression` explicit opt-in으로 보존한다. 모든 실행은 raw/effective 68 blendshape, 10 emotion JSON/CSV, 동기화 visualization, 최종 avatar+visualization hstack과 SHA/provenance를 manifest에 기록한다.

```bash
cd /home/aim/workspace/hosang/repo/facenet
scripts/audio2face-metahuman/run-a2f-metahuman.py /absolute/path/to/input.wav --name my-demo
```

v3 diffusion:

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /absolute/path/to/input.wav \
  --a2f-model v3.0-diffusion \
  --nim-url 127.0.0.1:52100 \
  --name my-v3-demo
```

표정/얼굴 파라미터 JSON:

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /absolute/path/to/input.wav \
  --a2f-model v3.0-diffusion \
  --motion-config scripts/audio2face-metahuman/configs/motion-expressive-safe-v1.json \
  --name expressive-safe
```

상세 공식 CES 목표/A-B/한계는 [v2.3↔v3.0 diffusion 검증](testing/audio2face-v23-v30-diffusion-benchmark.ko.md)을 참조한다.

아바타와 여러 named shot을 지정하는 예:

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /absolute/path/to/input.wav \
  --avatar Taro \
  --shot close-up-front \
  --shot medium-three-quarter-left \
  --shot medium-three-quarter-right \
  --shot profile-left \
  --name taro-four-shots
```

Unreal asset path도 허용한다.

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /absolute/path/to/input.wav \
  --avatar /Game/MetaHumans/Taro/BP_Taro.BP_Taro
```

GUI 클릭이나 `xdotool`은 반복 실행 경로에 사용하지 않는다. 실행 중이던 사용자 UnrealEditor PID는 종료하거나 재사용하지 않고, capture와 MRQ를 별도 `-Multiprocess` 프로세스로 실행한다.

## 아바타 선택과 공식 import 경계

CLI는 UE Asset Registry에서 `/Game/MetaHumans` 아래 Blueprint를 검색한다.

- 이름: `Taro`, `BP_Taro`, `Jesse`
- 정규 asset path: `/Game/MetaHumans/Taro/BP_Taro.BP_Taro`
- 이름이 없으면 추측하지 않고 exit `45`와 `manual_action_required` manifest를 남긴다.
- 같은 이름이 둘 이상이면 자동 선택하지 않고 exit `47`로 중단한다.
- 비기본 아바타는 base map을 run 전용 `RunMap`으로 저장·전환한 뒤 actor instance만 교체하고 ACE를 준비한다. 원본 Blueprint, material, map은 수정하지 않는다.

Epic 계정 로그인, Fab/MetaHuman 라이선스 승인, `Add to Project`, Bridge import/migrate, MetaHuman Creator 조립은 사용자 계정과 Editor UI가 필요한 공식 경계다. CLI는 Epic 토큰·쿠키를 읽거나 저장하지 않으며 이 단계를 우회하지 않는다. UE 5.6 설치본에는 MetaHuman Creator의 지원되는 unattended import/assembly entry point가 확인되지 않았고, 공개 MetaHuman Python 자동화 문서는 더 최신 UE 버전을 대상으로 하므로 5.6 자동 import로 간주하지 않는다.

없는 아바타를 지정한 뒤에는 다음 순서로 진행한다.

1. manifest의 `manual_action.official_docs` 링크를 연다.
2. Unreal Editor의 Fab/MetaHuman Creator/Bridge에서 로그인·라이선스 승인 후 현재 KairosSample 프로젝트에 추가한다.
3. `/Game/MetaHumans/<이름>/BP_<이름>`이 생겼는지 Content Browser에서 확인한다.
4. manifest의 `manual_action.resume_command`를 그대로 실행한다. 이 명령은 원 입력/config SHA를 확인하고 성공한 NIM preflight를 재사용하며 원래 named shot 또는 custom shot 파일도 보존한다.

공식 참고:

- [Epic: Buying MetaHumans from Fab](https://dev.epicgames.com/documentation/en-us/metahuman/buying-metahumans-from-fab)
- [Epic: MetaHuman Creator in Unreal Engine](https://dev.epicgames.com/documentation/en-us/metahuman/metahuman-creator-in-unreal-engine)
- [Epic: MetaHumans in Unreal Engine](https://dev.epicgames.com/documentation/en-us/metahuman/metahumans-in-unreal-engine)

## 카메라 shot

내장 preset은 다음 네 개다. `profile`은 `profile-left` 별칭이다.

| ID | 용도 |
| --- | --- |
| `close-up-front` | 얼굴 정면 클로즈업 |
| `medium-three-quarter-left` | 왼쪽 3/4 미디엄 |
| `medium-three-quarter-right` | 오른쪽 3/4 미디엄 |
| `profile-left` | 왼쪽 프로필 |

각 shot은 run 전용 spawnable `CineCameraActor`, 독립 LevelSequence와 Camera Cut을 사용한다. A2F/Take Recorder는 입력당 한 번만 실행하고 기록된 Face AnimSequence를 모든 shot이 재사용하며 MRQ만 shot별로 순차 실행한다.

사용자 지정 카메라는 versioned JSON으로 전달한다.

```json
{
  "schema_version": 1,
  "shots": [
    {
      "id": "custom-front-50mm",
      "camera": {
        "coordinate_space": "avatar_head",
        "location_cm": [0.0, 120.0, -8.0],
        "rotation_deg": [3.8, -90.0, 0.0],
        "focal_length_mm": 50.0,
        "aperture": 8.0,
        "focus_distance_cm": 120.0
      }
    },
    {"id": "profile", "preset": "profile-left"}
  ]
}
```

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /absolute/path/to/input.wav \
  --avatar Taro \
  --shot-config /absolute/path/to/shots.json \
  --name custom-shots
```

`coordinate_space`는 `avatar_head` 또는 `world`이고 `rotation_deg` 순서는 `[pitch, yaw, roll]`이다. 문서는 최대 1 MiB/16 shots이며, 알 수 없는 key, 중복/위험한 ID, NaN/Infinity, 범위 밖 transform은 exit `48`로 거부한다. `--shot`과 `--shot-config`는 동시에 쓸 수 없다.

## ECC 및 공식 자료 조사

적용한 ECC 스킬 순서:

1. `ecc:documentation-lookup`
2. `ecc:search-first`
3. `ecc:agentic-engineering`
4. `ecc:video-editing`

Context7 플러그인 리소스는 설치되어 있었지만 이 세션에는 `resolve-library-id`와 `query-docs` 실행 도구가 노출되지 않았다. 따라서 Context7 조회 불가 사실을 manifest에 기록하고 NVIDIA/Epic 공식 문서와 설치된 공식 소스를 직접 대조했다.

| 단계 | 사용한 공식 entry point |
| --- | --- |
| NIM health/inference | NVIDIA v2.0 `a2f_3d.py`, `HealthStub.Check()`, `A2FControllerServiceStub.ProcessAudioStream()` |
| UE A2F 호출 | `UACEBlueprintLibrary::AnimateCharacterFromWavFile`; 설치된 ACE 2.5에서는 게임 스레드 호출을 `UAsyncActionAnimateCharacter::AnimateCharacterFromWavFileAsync()`로 전달 |
| Capture | `UTakeRecorderSubsystem::SetTargetSequence`, `AddSourceForActor`, `StartRecording`, `StopRecording`, `TakeRecorderFinished` |
| MRQ | `MoviePipelinePythonHostExecutor`, `ExecutorPythonClass`, Epic `MoviePipelineExampleRuntimeExecutor.py` 구조 |
| MP4 | MRQ PNG 시퀀스 + 프로젝트 FFmpeg H.264/AAC mux |

공식 1차 자료:

- [NVIDIA Audio2Face-3D NIM v2.0 sample app](https://docs.nvidia.com/ace/audio2face-3d-microservice/2.0/text/interacting/sample-app.html)
- [NVIDIA Audio2Face-3D-Samples v2.0 source](https://github.com/NVIDIA/Audio2Face-3D-Samples/blob/a2d0150043be7dc15db2fad8193a78b660e1100f/scripts/audio2face_3d_microservices_interaction_app/a2f_3d.py)
- [NVIDIA ACE Unreal Audio2Face](https://docs.nvidia.com/ace/ace-unreal-plugin/latest/ace-unreal-plugin-audio2face.html)
- [NVIDIA ACE support matrix](https://docs.nvidia.com/ace/ace-unreal-plugin/latest/ace-unreal-plugin-support-matrix.html)
- [NVIDIA Kairos sample](https://docs.nvidia.com/ace/gaming-avatar/latest/gaming-avatar-unreal-sample-project.html)
- [Epic UE 5.6 Python automation](https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python?application_version=5.6)
- [Epic UE 5.6 Take Recorder](https://dev.epicgames.com/documentation/en-us/unreal-engine/take-recorder-in-unreal-engine?application_version=5.6)
- [Epic UE 5.6 MRQ command line](https://dev.epicgames.com/documentation/en-us/unreal-engine/using-command-line-rendering-with-move-render-queue-in-unreal-engine?application_version=5.6)
- [Epic MetaHumans in Unreal Engine](https://dev.epicgames.com/documentation/en-us/metahuman/metahumans-in-unreal-engine)

## 설치 버전

| 제품 | 검증 버전 |
| --- | --- |
| Audio2Face-3D NIM | 2.0, image digest `sha256:6112996e0cbfd7a09d8555712bf3d03142da7bed6cade8cddcf0a6308312df71` |
| Audio2Face-3D-Samples | tag `v2.0`, commit `a2d0150043be7dc15db2fad8193a78b660e1100f` |
| NVIDIA ACE Unreal Plugin | `2.5.0-20250614-2282` |
| Unreal Engine | `5.6.0`, changelist `43139311` |
| MetaHuman Taro | `4.1.2` |
| MetaHuman Jesse | `4.1.2` (로컬 readiness 시도, Vulkan blocker 기록) |

NVIDIA v2.0 NIM은 공식 문서대로 `nvidia_ace` Python module v1.2.0을 사용한다. ACE 2.5 문서는 async WAV node를 권장하며, 설치된 C++ 소스의 호환용 `AnimateCharacterFromWavFile`은 게임 스레드에서 async action을 생성한다.

## one-time Editor bootstrap

다음 항목은 현재 프로젝트에 이미 구성되어 있다.

- Taro Face에 NVIDIA ACE용 Face AnimBP와 `ACE Audio Curve Source` 적용
- RemoteA2F server URL `http://127.0.0.1:52000`
- `/Game/Maps/TaroA2F/TaroFaceBodyDemo_Repaired`와 focus `96.4 cm` 카메라
- `Takes`, `MovieRenderPipeline`, `PythonScriptPlugin`, `EditorScriptingUtilities` 활성화
- `Content/Python/init_unreal.py`에서 MRQ Python executor UClass 등록
- VNC PulseAudio/DBus/XDG 환경과 프로젝트 로컬 FFmpeg

반복 실행에서 별도의 GUI 조작은 필요하지 않다. 이 bootstrap이 없는 다른 프로젝트에서는 Editor에서 최초 1회 설정해야 한다.

## 실행 단계

1. 입력을 NIM용 PCM16 mono 16 kHz와 최종 mux용 PCM16 mono 48 kHz로 변환한다.
2. NVIDIA 공식 `a2f_3d.py health_check`와 `run_inference`를 그대로 호출해 CSV/WAV 결과를 검증한다.
3. 별도 UnrealEditor에서 `TakeRecorderSubsystem`으로 Taro를 source에 추가하고 PIE를 시작한다.
4. 실제 recorder state가 `TakeRecorderState.STARTED`가 된 후 공식 ACE WAV 함수를 호출한다.
5. `OnAnimationEnded`에서 recorder를 정지하고 `TakeRecorderFinished`에서 Face AnimSequence를 확보한다.
6. 실제 animation start offset을 반영한 최종 LevelSequence를 저장한다.
7. Epic 방식의 `MoviePipelinePythonHostExecutor + ExecutorPythonClass` 명령으로 120 PNG를 렌더한다.
8. FFmpeg로 H.264/AAC MP4를 만들고 frame/motion/audio/A/V/decode gate를 수행한다.

NVIDIA 공식 client preflight와 ACE RemoteA2F capture는 서로 다른 검증 단계이므로 NIM inference가 두 번 실행된다. CSV를 비공식 importer로 UE에 주입하지 않는다.

## 최종 검증 실행

입력:

```text
.tools/audio2face3d/cli-inputs/cli-new-speech.wav
SHA-256: 5311ea28b6010a5c0be0a7a671b0e60f9967e9b33b580569852dd3f2b7572b9e
duration: 4.000000 s
```

성공 run:

```text
.tools/audio2face3d/official-cli-runs/20260826-221250-hybrid-new-speech-final/
```

결과:

| Gate | 결과 |
| --- | --- |
| NVIDIA official client | `ONLINE`, `Status code: SUCCESS` |
| NIM blendshape | 120 frames, 68 columns, finite, monotonic, max delta `0.7724867` |
| ACE/Take Recorder | 120 samples, 192000 audio samples, capture offset `0.266374 s` |
| MRQ | 120 contiguous PNG, sampled frame hashes 3/3 unique |
| Video | H.264 High, 1920×1080, 30 fps, 120 frames, 4.000 s |
| Audio | AAC, 48 kHz mono, 4.000 s, mean `-32.2 dBFS`, max `-9.4 dBFS` |
| A/V | start delta `0 ms`, duration delta `0 ms` |
| Decode | video+audio full decode PASS |
| MP4 SHA-256 | `0472d06c5c3dffd78422e87e666b7fdf2841e26a4854962e90ac58478504a0a1` |

최종 MP4:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260826-221250-hybrid-new-speech-final/taro-a2f-hybrid-new-speech-final-final.mp4
```

증거:

```text
manifest.json
official-inference-verification.json
capture-status.json
capture-ue.log
mrq-config.json
mrq.log
verification.json
ffprobe.json
ffmpeg-volume.log
ffmpeg-astats.log
motion-montage.png
vnc-playback-final-clean.png
```

## exit code

| code | 의미 |
| ---: | --- |
| 0 | 전체 성공 |
| 10 | preflight 실패 |
| 20 | 공식 NVIDIA NIM client 실패 |
| 42 | capture 실패 또는 `--inference-only` 경계 |
| 43 | Epic MRQ executor 실패 |
| 44 | mux/ffprobe/frame/motion/audio/decode 실패 |
| 45 | MetaHuman이 로컬에 없음: 공식 Epic UI import 필요 |
| 46 | Face/Face_AnimBP/ACE instance 준비 실패: Editor bootstrap 필요 |
| 47 | 아바타 path/name 해석 실패 또는 모호함 |
| 48 | named/custom shot 설정 검증 실패 |

## manifest v2와 결과 구조

`manifest.json`의 `schema_version`은 2이며 다음을 기록한다.

- `avatar_request`, 정규화된 `avatar.object_path`, 해석 방식, actor label, `source_asset_modified`
- `shot_request`와 각 `shots[]`의 ID, preset/custom camera, resolved world transform, LevelSequence, frames, MP4, 검증 결과
- `resumed_from`, input/config SHA, 공식 NVIDIA inference entry point와 output
- 제품 버전, 공식 URL/API symbol, 정확한 subprocess argv와 로그
- 누락 asset이면 인증 경계, 공식 import 링크와 원 shot 요청을 보존한 `resume_command`

여러 shot은 `<run>/shots/<shot-id>/`에 저장된다. 기존 무옵션 Taro 단일 shot은 이전 파일명과 top-level `verification`, `final_mp4`를 그대로 유지한다.

## 멀티 아바타·멀티 shot 실제 검증

기본 동작 및 실제 발화 회귀:

```text
.tools/audio2face3d/official-cli-runs/20260827-095728-test-wav-visible-a2f-final/
```

- 입력 `/home/aim/Downloads/test.wav`, 무옵션 Taro + `close-up-front`
- exit 0, 109 frames, H.264/AAC, 48 kHz mono, non-silent, A/V start 0 ms, full decode PASS
- mouth curve 24개, 최대 범위 약 `0.54`, Face animation track 정확히 1개
- 24-frame mouth contact sheet와 발화 프레임에서 반복적인 입 벌림·치아 노출 확인
- 기존 `taro-a2f-<label>-final.mp4`와 top-level manifest contract 유지

네 개 preset shot:

```text
.tools/audio2face3d/official-cli-runs/20260827-100106-test-wav-four-visible-final/
```

- 한 번의 ACE/Take Recorder capture 뒤 MRQ 4회
- `close-up-front`, 좌/우 3/4, `profile-left` 모두 120 frames와 서로 다른 카메라 transform/프레임 SHA
- 각 MP4 H.264/AAC, 109 frames, 48 kHz mono, non-silent, A/V start 0 ms, full decode PASS
- 네 구도 모두 한 개의 face animation track과 실제 입 움직임 확인
- 시각 증거: `four-shot-motion-contact.png`

수정된 사용자 지정 transform:

```text
.tools/audio2face3d/official-cli-runs/20260827-100621-test-wav-custom-visible-final/
```

- `avatar_head` 위치 `[0,120,-8]`, `[pitch,yaw,roll]=[3.8,-90,0]`, 50 mm
- resolved rotation `[3.79999995,-90,0]`; Taro 얼굴·헤어·의상이 프레임 안에 있음을 중간 프레임으로 시각 확인
- H.264/AAC, 109 frames, 48 kHz mono, A/V 0 ms, full decode PASS
- custom front contact sheet에서 입술 폐쇄/개방과 치아 노출 확인

없는 아바타 경계:

```text
.tools/audio2face3d/official-cli-runs/20260827-000315-gate2-final-missing/
```

- `DoesNotExist`는 exit 45
- status `manual_action_required`, 공식 Fab/Creator/ACE 링크 기록
- 토큰/쿠키 접근이나 비공식 다운로드 없음

비기본 로컬 Jesse:

```text
.tools/audio2face3d/official-cli-runs/20260827-000412-gate2-final-jesse/
```

- 정규 asset path 해석, run-owned `RunMap`, BP_Jesse spawn, Face mesh + Face_AnimBP + ACE component 준비까지 PASS
- 당시 run-owned map 격리는 유지됐지만 이후 잘못된 raw binary 복구로 기존 base map 내부 package reference가 손상됨. 손상본은 진단 폴더에 보존하고 정상 직렬화된 `TaroFaceBodyDemo_Repaired`를 현재 기본 map으로 사용
- PIE 렌더 시작에서 UE 5.6 Linux Vulkan `VkResult=-13`, `VulkanPipeline.cpp:1666`으로 종료되어 Jesse MP4는 성공 산출물로 인정하지 않는다.
- 이 blocker는 아바타 선택/공식 import 실패가 아니라 현재 Jesse 의상 material과 Vulkan renderer 조합의 알려진 로컬 제약이다. 드라이버 변경이나 material 대체를 이 기능에서 자동 실행하지 않는다.

## 테스트와 보안 검토

- Python tests: 39 PASS
- 순수 avatar/shot/resume/manifest helper coverage: 89%
- invalid named shot 실제 exit: 48
- 사용자 shot JSON: strict key/size/count/numeric range 검증
- 모든 subprocess는 argv list로 실행하며 `shell=True` 없음
- Unreal/MRQ child 환경은 DISPLAY/Xauthority/Pulse/Vulkan/CUDA/기본 locale·library 변수 allowlist만 전달하며 token과 SSH/GPG/Kerberos agent capability는 전달하지 않음
- 소스와 검증 대상 파일에서 토큰 형태 secret pattern 0건
- map/sequence는 안전한 `/Game/...` reference만 허용하여 Unreal option injection을 차단
- MRQ frames 경로는 신규 또는 빈 non-symlink 디렉터리만 허용
- resume은 성공 상태, input/config SHA와 공식 inference 네 파일의 size/SHA를 다시 검증
- fps/해상도/frame count/timeout/audio duration·size를 제한하고 remote NIM은 명시적 `--allow-remote-nim` 필요
- 실패/timeout 정리는 CLI가 만든 새 process group에 TERM→bounded wait→KILL→reap을 적용하며 실행 중인 사용자 UnrealEditor PID `1224942`는 유지됨
- leader 종료 뒤 같은 PGID에 child만 남는 실제 subprocess 통합 테스트에서 잔존 headless UE 0건 확인

### 폐기한 잘못된 성공 증거

`20260826-235435-gate2-final-default`, `20260826-235625-gate2-final-four`, `20260827-000057-gate2-final-custom`, `20260827-001113-gate2-final-postcleanup`은 video/audio/decode gate만 통과했고 얼굴은 거의 neutral이었다. 원인은 기본 map 파일 내부 self-reference가 다른 `RunMap` package를 가리킨 상태였기 때문이다. 이 run들은 진단 증거로만 보존하며 Audio2Face 발화 성공으로 간주하지 않는다.

## 진단 코드 경계

`run-a2f-taro-cli.py`, `Scripts/ue_a2f_cli_pipeline.py`, 기존 r1–r4 run은 진단 증거로만 보존한다. production entry point와 `init_unreal.py`는 이를 호출하지 않는다. 기존 clip별 finalizer와 `run-a2f-taro-official.py`는 호환용으로 남아 있으며 신규 작업은 범용 `run-a2f-metahuman.py` 또는 그 `--finalize-only` 모드를 사용한다.
