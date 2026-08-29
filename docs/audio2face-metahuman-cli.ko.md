# Audio2Face-3D → 범용 MetaHuman CLI 사용 설명서

## 바로 실행하기

이 저장소의 사용자용 명령은 `run-a2f-metahuman.py`다. 오디오 하나를 NVIDIA Audio2Face-3D, ACE 2.5, UE 5.6 Take Recorder, Movie Render Queue와 프로젝트 FFmpeg에 순서대로 전달해 최종 H.264/AAC MP4와 진단 영상을 만든다. 2026-08-27부터 canonical 기본 모델은 `v3.0-diffusion`/`multi_v3.2`/`127.0.0.1:52100`이다. 기본 avatar와 shot은 `Taro`, `close-up-front`다.

```bash
cd /home/aim/workspace/hosang/repo/facenet

scripts/audio2face-metahuman/run-a2f-metahuman.py /home/aim/Downloads/test.wav \
  --name my-metahuman-demo
```

위 명령은 모델 옵션을 생략해도 v3 diffusion을 사용한다. native v3를 기본으로 할 뿐 과도한 motion 후처리를 묵시적으로 켜지는 않는다. 검증된 dynamic-safe final-render를 명시하려면 다음처럼 실행한다.

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /home/aim/Downloads/test.wav \
  --avatar Taro \
  --shot close-up-front \
  --motion-config scripts/audio2face-metahuman/configs/motion-v3-dynamic-safe-final-v1.json \
  --progress auto \
  --name default-v30
```

legacy v2.3 regression은 삭제되지 않았으며 반드시 명시적으로 선택한다.

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /home/aim/Downloads/test.wav \
  --a2f-model v2.3-regression \
  --name legacy-v23
```

이때 endpoint를 생략하면 v2는 52000, v3는 52100을 선택한다. v3 health/model/cadence 검증 실패 시 v2로 자동 fallback하지 않으며 `start-a2f-v3-diffusion.sh` 실행 안내와 nonzero exit를 남긴다.

기존 `run-a2f-taro-official.py`는 삭제하지 않았다. 모든 인자와 exit code/stdout을 새 명령으로 전달하되 stderr에 deprecation 경고를 한 번 출력하는 호환 wrapper다. wrapper도 no-option이면 v3 기본값을 사용한다.

### 기본 모델 변경·resume migration

이번 변경은 no-option 명령의 동작이 v2.3에서 v3.0으로 바뀐 behavioral breaking change다.

- 신규 no-option run: v3.0 diffusion/52100
- 명시적 `--a2f-model v2.3-regression`: 기존 v2/52000 완전 지원
- 기존 v2 resume에서 model 옵션 생략: source manifest의 v2/52000 상속
- v3 resume에서 model 옵션 생략: source manifest의 v3/52100 상속
- resume source와 명시적 model/endpoint가 다름: 재사용 거부. 새 cross-model inference는 `--resume` 없이 실행
- client의 `config_claire.yml`은 모델 선택 파일이 아니라 Claire용 공통 request header다. 실제 regression/diffusion 선택은 attested NIM service/model에서 수행한다.

## 다른 MetaHuman 선택

로컬 프로젝트에 이미 들어온 MetaHuman은 이름, `BP_` 이름 또는 정규 Unreal asset path로 선택할 수 있다.

```bash
# 이름
scripts/audio2face-metahuman/run-a2f-metahuman.py input.wav --avatar Ada --name ada-demo

# 정규 asset path
scripts/audio2face-metahuman/run-a2f-metahuman.py input.wav \
  --avatar /Game/MetaHumans/Ada/BP_Ada.BP_Ada \
  --name ada-by-path
```

CLI는 `/Game/MetaHumans` Asset Registry에서 유일한 Blueprint를 찾고 run 전용 map/sequence/AnimSequence만 만든다. 원본 MetaHuman Blueprint, material과 map은 수정하지 않는다. 아바타가 없으면 exit `45`와 `manual_action_required` manifest를 남긴다. Epic/Fab 로그인, 라이선스 승인, MetaHuman Creator/Fab의 `Add to Project`는 계정 소유자가 Unreal Editor에서 한 번 수행해야 하는 공식 경계이며 CLI는 이를 우회하거나 Epic 자격증명을 읽지 않는다. 가져온 뒤 manifest의 `resume_command`를 실행하면 된다.

Linux Vulkan에서 source clothing shader가 `VkResult=-13`으로 실패하는 MetaHuman에는 명시적으로 run-owned presentation profile을 사용할 수 있다.

```bash
python3 scripts/audio2face-metahuman/run-a2f-metahuman.py \
  /home/aim/Downloads/test.wav \
  --avatar Sook-ja \
  --avatar-visual-profile face-focused-vulkan-safe \
  --motion-config scripts/audio2face-metahuman/configs/motion-v3-dynamic-safe-final-v1.json
```

`face-focused-vulkan-safe`는 원본 BP/mesh/material을 변경하지 않는다. run-owned actor instance에서 Face, Body와 모든 groom을 유지하고, Torso slot만 검증된 opaque material로 override하며 Legs/Feet를 숨긴다. 기본값 `source`는 기존 Taro 동작을 그대로 보존한다.

## 카메라와 여러 구도

named preset은 `close-up-front`, `medium-three-quarter-left`, `medium-three-quarter-right`, `profile-left`다. 한 입력에서 한 번 capture한 얼굴 animation을 각 shot의 독립 카메라/MRQ render가 재사용한다.

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py input.wav \
  --avatar Taro \
  --shot close-up-front \
  --shot medium-three-quarter-left \
  --shot medium-three-quarter-right \
  --shot profile-left \
  --name four-shots
```

사용자 shot은 strict schema JSON으로 전달한다.

```json
{
  "schema_version": 1,
  "shots": [
    {
      "id": "front-50mm",
      "camera": {
        "coordinate_space": "avatar_head",
        "location_cm": [0.0, 120.0, -8.0],
        "rotation_deg": [3.8, -90.0, 0.0],
        "focal_length_mm": 50.0,
        "aperture": 8.0,
        "focus_distance_cm": 120.0
      }
    }
  ]
}
```

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py input.wav \
  --shot-config /absolute/path/to/shots.json \
  --name custom-camera
```

NaN/Infinity, 알 수 없는 key, 중복/위험한 ID, 허용 범위 밖 transform은 실행 전에 거부한다.

## 감정·얼굴·curve 설정의 실제 적용 경계

motion config는 `schema_version: 1`이며 `curve_application`을 반드시 명시한다. 일반 `artifact_only`는 raw/effective JSON·CSV와 진단 화면만 바꾼다. 예외적으로 `nvidia_runtime_curve_parameters`를 지정하면 공식 `FAnimNode_ApplyACEAnimation`의 multiplier/offset map을 run-owned PIE AnimInstance에 설정해 capture 순간부터 최종 MP4에 적용한다. `final_render`는 run 전용 captured AnimSequence의 float curve를 bulk bake하지만, 이미 bake된 MetaHuman bone pose를 다시 평가하지 않는 curve가 있으므로 단독 시각 품질 향상 경로로 간주하지 않는다. NVIDIA raw CSV와 pre-transform AnimSequence는 항상 보존된다.

| 입력 필드 | NVIDIA inference | ACE capture | captured AnimSequence | 최종 MP4 |
| --- | --- | --- | --- | --- |
| named/custom shot, transform, focal/aperture/focus | 해당 없음 | 카메라 생성 | LevelSequence/CameraCut | 적용 |
| `face_parameters` | 공식 request config | ACE 2.5 WAV parameters | capture 결과에 포함 | 적용 |
| constant emotion, `overall_strength` | 공식 emotion override | ACE emotion override | capture 결과에 포함 | 적용 |
| timecoded emotion | 공식 request conditioning | WAV helper의 직접 시계열 API 없음 | `final_render`일 때 effective curve bake | 조건부 적용 |
| global/region/per-curve gain·bias·clamp, attack/release | raw에는 미적용 | 직접 API 없음 | `final_render`일 때 52 curve bulk bake | 조건부 적용 |
| `nvidia_runtime_curve_parameters` multiplier/offset | official client CSV에 적용 | 공식 `Apply ACE Face Animations` node map에 동일 값 적용 | Take Recorder가 결과 pose/curve capture | 적용; node-count/map lineage와 content-sync 필수 |
| 16개 extended tongue curve | 68-curve artifact에 보존 | 설치된 ACE 2.5 renderer가 직접 소비하지 않음 | bake 거부 | artifact/마네킹 전용 |

허용되는 ACE 2.5 얼굴 parameter는 설치 소스와 같은 이름을 쓴다: `skinStrength`, `upperFaceStrength`, `lowerFaceStrength`, `eyelidOpenOffset`, `blinkStrength`, `lipOpenOffset`, `upperFaceSmoothing`, `lowerFaceSmoothing`, `faceMaskLevel`, `faceMaskSoftness`, `tongueStrength`, `tongueHeightOffset`, `tongueDepthOffset`, `inputStrength`, `blinkOffset`. 이름과 공식 범위를 preflight에서 검사한다.

예제는 다음 세 파일이다.

- `configs/motion-baseline-v1.json`: 기존 기본 동작
- `configs/motion-expressive-safe-v1.json`: `final_render`, lower/upper face parameter와 제한된 curve postprocess
- `configs/motion-v3-dynamic-safe-final-v1.json`: v3 전용 검증 preset. final-render, upper saturation 0건, jaw/mouth/upper-face/eye activity 확대
- `configs/motion-v3-ace-node-quality-v4.json`: 공식 ACE 52-source node map을 이용한 opt-in 품질 preset. blink 8×, eye-wide 0.8×이며 이 입력에서는 saturation 0건이다.

effective config, 입력/config/model hash, runtime/weight identity, raw/effective provenance는 run의 `manifest.json`과 `motion-artifacts/effective-motion-config.json`에 기록된다.

## clean face-mesh 마네킹 패널

각 실행은 공식 NVIDIA client의 `animation_frames.csv`에 있는 실제 A2F-68 시계열로 다음 geometry를 직접 변형한다.

- skin: Claire neutral 1,500 vertex + 52 blendshape delta
- tongue: Claire neutral 520 vertex + 16 extended tongue delta
- surface: Claire `template.usd`에서 추출한 skin 2,996 triangle + tongue 1,036 triangle
- render: 단순 청색 중립 재질의 antialiased triangle surface

따라서 이 패널은 curve 그래프, point cloud, MetaHuman 영상 재색칠이 아니다. zero weight는 neutral geometry로 되돌아가고, 다른 curve frame은 geometry SHA와 frame SHA가 달라진다. raw/effective 두 영상을 각각 저장하며 `curve_application=final_render`이면 comparison에는 effective를 선택한다.

다만 이는 선택한 MetaHuman mesh가 아니라 NVIDIA Claire solver basis를 사용한 진단용 마네킹이다. v3 diffusion의 direct vertex 출력도 아니며, NIM solver가 출력한 68 curve가 Claire basis에서 만드는 변형을 보여준다. Claire sample dataset은 evaluation-only이므로 이 시각화 자산도 그 범위에서 사용해야 한다.

최종 진단 영상은 1920×1080 3-panel이다.

- 왼쪽: 최종 MetaHuman avatar
- 오른쪽 위: blendshape-driven clean mannequin surface
- 오른쪽 아래: 현재 effective 값 내림차순 Active Curves 8개, raw/effective bar, 68-curve strip. Emotion은 화면에서 제외하며 JSON/CSV에는 보존
- 오디오: 최종 avatar MP4와 같은 authoritative 입력 WAV 기반 AAC

## 진행 표시

`--progress auto|always|never`를 지원한다.

- `auto`: TTY에서는 한 줄 spinner/bar, pipe/CI에서는 ANSI 없는 단계별 행
- `always`: redirection 여부와 무관하게 사용자 진행 UI 표시
- `never`: stderr 진행 UI를 끄고 기존 script 동작 유지

진행률은 완료한 실제 stage, MRQ의 실제 생성 frame 수에만 사용한다. NIM/UE 시작처럼 전체량을 모르는 단계는 percent 대신 spinner와 elapsed만 표시한다. stdout의 기존 `SUCCESS <paths>` 계약은 바뀌지 않으며 모든 progress는 stderr다. 동일 이벤트는 `<run>/progress-events.jsonl`에도 저장된다.

대표 출력:

```text
[A2F][04/11][nim_inference] PASS frames=218 curves=68 elapsed=3.1s
[A2F][07/11][mrq] RUN 61/109 frame 61/109
[A2F][10/11][hstack] PASS avatar + mannequin(effective) + curves 1920x1080
[A2F][11/11][complete] 100% elapsed=144.2s manifest=.../manifest.json
```

## 결과 폴더

```text
<run>/
  manifest.json
  progress-events.jsonl
  capture-status.json
  <avatar>-a2f-<name>-final.mp4
  <avatar>-a2f-<name>-final-a2f-diagnostic-triptych.mp4
  motion-artifacts/
    blendshapes.raw.{json,csv}
    blendshapes.effective.{json,csv}
    emotion.input.{json,csv}
    emotion.smoothed.{json,csv}
    blendshape-visualization.mp4
    mannequin/mannequin.raw.mp4
    mannequin/mannequin.effective.mp4
    artifact-manifest.json
  shots/<shot-id>/
```

각 artifact path/SHA-256, schema/version, frame/fps, codec, A/V 시작차, decode 결과는 manifest에 연결된다. 단일-shot의 기존 top-level `final_mp4`와 `verification` 필드도 유지한다.

알려진 로컬 runtime은 모델과 포트를 묶어서 검증한다: v2.3 regression은 `127.0.0.1:52000`, v3 diffusion은 `127.0.0.1:52100`이다. 두 포트를 반대로 지정하면 preflight에서 거부한다. 그 밖의 custom loopback/remote endpoint는 실행할 수 있지만 manifest의 runtime은 `unattested`이며, 이 서버의 container/engine/model hash를 해당 서비스의 증거처럼 기록하지 않는다.

## 2026-08-27 최종 검증

실행:

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /home/aim/Downloads/test.wav \
  --name generic-controls-bulk-final-e2e \
  --a2f-model v3.0-diffusion \
  --nim-url 127.0.0.1:52100 \
  --avatar Taro \
  --shot close-up-front \
  --motion-config scripts/audio2face-metahuman/configs/motion-expressive-safe-v1.json \
  --progress auto \
  --capture-timeout 600 --mrq-timeout 600
```

run:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-140813-generic-controls-bulk-final-e2e/
```

검증 결과:

| 항목 | 결과 |
| --- | --- |
| 공식 v3 inference | 218 raw frames, 68 curves, finite/monotonic PASS |
| ACE/Take Recorder | pre-transform 보존, effective 복제 asset에 52 curves × 218 keys bulk 적용 |
| 최종 avatar | H.264 1920×1080, 30 fps, 109 frames |
| 진단 triptych | H.264/AAC 1920×1080, 109 frames, full decode PASS |
| 오디오 | AAC, 48 kHz mono, non-silent |
| A/V | start delta 0 ms, duration delta 7.333 ms |
| 마네킹 | raw/effective 각각 H.264 640×540, 109 frames, 서로 다른 sample geometry/frame SHA |
| progress | 46 JSONL events, 실제 MRQ 0/109→109/109 |
| 회귀 테스트 | 118 PASS + 6 subtests (선택 모듈 합산 coverage 83%) |

진단 triptych:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-140813-generic-controls-bulk-final-e2e/taro-a2f-generic-controls-bulk-final-e2e-final-a2f-diagnostic-triptych.mp4
SHA-256: b330e4789ea8d2f98fb0653ef99a17c346dbd6428d037e946a2209b520aec914
```

확인 이미지:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-140813-generic-controls-bulk-final-e2e/diagnostic-triptych-frame-1.633.png
```

## 공식 근거와 구현 symbol

- NVIDIA inference: 공식 `a2f_3d.py`, `A2FControllerServiceStub.ProcessAudioStream()`
- ACE: `UACEBlueprintLibrary::AnimateCharacterFromWavFile`, `UAsyncActionAnimateCharacter::AnimateCharacterFromWavFileAsync`
- capture: `UTakeRecorderSubsystem::{SetTargetSequence,AddSourceForActor,StartRecording,StopRecording}`
- curve bake: Epic `IAnimationDataController::FScopedBracket`, `AddCurve`, `SetCurveKeys`
- MRQ: `MoviePipelinePythonHostExecutor`, `ExecutorPythonClass`

1차 자료:

- <https://github.com/NVIDIA/Audio2Face-3D>
- <https://github.com/NVIDIA/Audio2Face-3D-SDK/blob/main/docs/README.md>
- <https://huggingface.co/nvidia/Audio2Face-3D-v3.0>
- <https://docs.nvidia.com/ace/ace-unreal-plugin/latest/ace-unreal-plugin-audio2face.html>
- <https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/TakeRecorderSubsystem?application_version=5.6>
- <https://dev.epicgames.com/documentation/en-us/unreal-engine/using-command-line-rendering-with-move-render-queue-in-unreal-engine?application_version=5.6>

## 로컬 자연스러운 머리 움직임

NVIDIA A2F/ACE 2.5가 머리 움직임을 생성하는 기능은 아니다. 이 기능은 입력 WAV의 음성 activity에서 저주파 pitch/yaw/roll sample을 결정적으로 만들고, Take Recorder가 만든 run-owned Body/Face `AnimSequence` 복사본에 Epic `IAnimationDataController`로 목·머리 회전 키를 bake하는 로컬 확장이다. MetaHuman 원본 Blueprint·animation·camera·actor root는 수정하지 않는다.

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py \
  /home/aim/Downloads/test.wav \
  --resume .tools/audio2face3d/official-cli-runs/20260828-085258-hands-on-default-v30/manifest.json \
  --avatar Taro \
  --shot close-up-front \
  --motion-config scripts/audio2face-metahuman/configs/motion-head-subtle-v1.json \
  --head-motion subtle-conversational \
  --head-motion-strength 1.0 \
  --name taro-head-motion
```

- `--head-motion`: `off`(기본값) 또는 `subtle-conversational`
- `--head-motion-strength`: 활성 profile에서만 `0.0–1.5`
- config preset: `scripts/audio2face-metahuman/configs/motion-head-subtle-v1.json`
- sample/CSV/metrics와 별도 SHA lineage를 `<run>/head-motion/`에 저장한다.
- Body의 `neck_01 → neck_02 → head`에는 각각 20%/30%/50%, 독립 Face mesh의 `head`에는 동일 master clock의 100% 회전을 적용한다.
- `--finalize-only`와 caller-owned `--level-sequence`는 적용할 UE stage가 없어 활성 시 거부한다.
- Keiji는 `source` clothing Vulkan PSO guard 때문에 `face-focused-vulkan-safe` 없이는 launch하지 않는다.

검증된 Taro ON run은 `20260829-110741-head-motion-sync-final-r7`이다. 동일 inference·음성·얼굴 curve·고정 카메라의 OFF/ON을 비교했다. 머리 움직임은 같은 avatar/shot baseline의 실측 content-sync lag를 `--resume` manifest에서 가져와 bone bake를 반대 방향으로 보상한다. 측정값과 최종 보정값이 다르면 exit `44`로 실패하므로 고정된 magic offset을 추측하지 않는다.

| 검증 | 결과 |
| --- | --- |
| 본 키 | Body 327 keys(109×3), Face head 109 samples; `neck_01` 0.342°, `neck_02` 0.513°, `head` 0.855° authored max delta |
| 실제 렌더 움직임 | OFF 대비 머리 회전 RMS 0.154°, p95 0.296°; 화면 이동 RMS x 1.42 px, y 4.40 px |
| 영상 | H.264/AAC, 1920×1080, 30 fps, 109 frames, full decode PASS |
| 동기 | A/V start 0 ms, JawOpen content lag 0 frame, correlation 0.808 |
| 보존 | 카메라 transform 동일, actor-root track 없음, Face curve SHA와 단일 Face track 동일 |
| 머리 master clock | source-audio 기준 optical best lag -1 frame(허용 ±1), zero-lag multivariate R² 0.994 |

확인할 파일:

```text
.tools/audio2face3d/official-cli-runs/20260829-110741-head-motion-sync-final-r7/
  taro-a2f-head-motion-sync-final-r7-v30-diffusion-final.mp4
  head-motion-off-on-comparison.mp4
  head-motion-off-on-contact-sheet.png
  head-motion-final-verification.json
```

새 오디오에서는 먼저 같은 avatar/shot으로 기본(head OFF) run을 한 번 만든 뒤, 그 manifest를 위 명령의 `--resume`에 지정한다. 이 baseline은 얼굴의 실제 render latency를 측정하는 calibration이며, NIM inference와 face curve도 hash 검증 후 재사용한다.

실행별 얼굴 latency가 baseline과 2 frames 이상 달라 strict gate가 중단되면, 실패 run이 남긴 검증된 observation을 다음 bounded retry에 명시할 수 있다.

```bash
--head-motion-calibration-manifest /absolute/path/to/head-motion-retry-calibration.json
```

이 옵션은 임의 숫자를 받지 않는다. 동일 input/model/avatar/shot/fps와 최소 correlation을 통과한 prior-attempt JSON만 허용하며 최종 residual은 여전히 ±1 frame 이하여야 한다.

### 로컬 MetaHuman 전체 검증

프로젝트에 설치된 네 MetaHuman을 모두 실제 렌더했다. Taro는 source, clothing Vulkan 이력이 있는 나머지는 run-owned `face-focused-vulkan-safe`를 사용했다.

| Avatar | Shot | Face lag / correlation | Head lag / R² | 결과 |
| --- | --- | --- | --- | --- |
| Taro | close-up-front | 0 / 0.808 | -1 / 0.995 | PASS |
| Keiji | medium-three-quarter-left | 0 / 0.825 | 0 / 0.996 | PASS |
| Sook-ja | medium-three-quarter-left | 0 / 0.956 | 0 / 0.998 | PASS |
| Jesse | close-up-front | 0 / 0.938 | 0 / 0.998 | PASS |

네 결과 모두 H.264/AAC 1920×1080, 30 fps, 109 frames, A/V 0 ms, full decode PASS이며 `neck_01/neck_02/head` authored delta가 nonzero다.

```text
.tools/audio2face3d/official-cli-runs/20260829-head-motion-all-avatars/
  all-avatars-head-motion-on.mp4
  all-avatars-head-motion-on-atlas.png
  all-avatars-head-motion-verification.json
```

## 알려진 한계

- Claire 저해상도 surface는 clean geometry 진단용이라 눈·치아·헤어와 MetaHuman 고해상도 피부를 재현하지 않는다.
- 설치된 ACE 2.5는 16개 extended tongue curve를 최종 MetaHuman render에 직접 소비하지 않으므로 final-render postprocess 대상에서 거부한다. raw/effective artifact와 mannequin에는 보존된다.
- v3 direct geometry의 skin/jaw/tongue/eye 정보는 NIM solver의 68 blendshape로 변환된 뒤 이 경로에 들어오므로 일부 세부 정보가 손실될 수 있다.
- 설치된 ACE 2.5 `FAnimNode_ApplyACEAnimation`의 `HeadBone`은 `not yet implemented`/`#if 0`이다. 위 opt-in 경로는 NVIDIA가 생성한 head motion이 아니라 별도 local AnimSequence bake extension이다.
- 이 입력의 official solver `TongueOut`은 전 프레임 0이라 `tongueStrength`만 높여도 혀가 보이지 않는다. extended tongue 16개를 MetaHuman에 억지로 bake하지 않는다.
- UE 5.6 Linux/Vulkan 별도 Editor 시작 SIGSEGV가 간헐적이다. CLI는 bounded timeout/failure manifest를 남기며 기존 사용자 UnrealEditor나 성공 run을 종료·수정하지 않는다.

## 2026-08-27 lip-sync와 수치 패널 개선

`ffprobe`의 stream `start_time=0`만으로는 실제 입 모양과 오디오 내용의 동기를 보장할 수 없다. CLI는 최종 avatar를 160×90 grayscale로 축소한 뒤 고정 ROI에 의존하지 않는 PCA motion feature를 만들고, 같은 프레임 시각의 A2F `JawOpen`과 -18..+18 frame 범위에서 상관을 계산한다. 양수 lag는 avatar가 A2F curve보다 늦다는 뜻이다.

- 상관계수 0.75 이상이고 ±1 frame 밖이면 `misaligned`다.
- run이 소유한 원본을 `*-pre-sync.mp4`로 보존하고 video frame만 trim/pad한다. authoritative AAC는 이동하거나 다시 생성하지 않는다.
- 보정 뒤 반드시 다시 측정해 `aligned`가 아니면 exit `44`로 실패한다.
- `final_render`에서 측정이 `inconclusive`여도 성공 처리하지 않는다.

최종 검증 run:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-143129-sync-content-final-e2e/
```

| 검증 | 보정 전 | 보정 후 |
| --- | ---: | ---: |
| avatar motion lag | +5 frames / +166.667 ms | 0 frames / 0 ms |
| JawOpen correlation | 0.940 | 0.942 |
| stream start delta | 0 ms | 0 ms |
| frame/decode | 109 / PASS | 109 / PASS |

오른쪽 아래 수치 패널은 `triptych-compact-v3`로 바뀌었다. 기존 960×1080 패널의 작은 기본 글꼴을 640×540로 축소하던 방식을 중단하고, 최종 표시 크기 640×540에 직접 렌더한다.

- 24 px 제목, 나머지 표시 문자 최소 16 px
- tabular 숫자와 frame/time을 우측 정렬
- 68개 curve 전체는 두 줄 heat strip으로 유지
- subtitle 아래 clip timeline에 현재 frame/time playhead 표시
- 화면에는 **현재 프레임 effective 값 내림차순** 상위 8개 curve의 이름, 값, 두꺼운 raw/effective bar 표시
- curve 순위는 매 프레임 다시 계산하며 같은 값은 NVIDIA canonical curve 순서로 안정적으로 정렬
- emotion 영역은 패널에서 제거했다. 10개 emotion 원본 JSON/CSV는 분석용으로 모두 보존
- 기존 상세 `blendshape-visualization.mp4`는 호환용으로 그대로 보존

다음 파일은 historical v2.3 readability 증거다. 파일명 끝의 `v3`는 과거 layout revision 의미였으며 model v3가 아니다. 혼동을 일으킨 이름이므로 신규 결과/문서에서는 사용하지 않고 `layout-vN`으로 분리한다.

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-144232-default-v23-readable-sync-final/taro-a2f-default-v23-readable-sync-final-sorted-no-emotion-v3.mp4
SHA-256: 25333663eb6ddfaf564c6080e0c9301a5142c6f053db8118e22340032cefb55c
```

확인 이미지:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-144232-default-v23-readable-sync-final/sorted-no-emotion-v3-frame-1.633.png
```

이 파일은 H.264/AAC, 1920×1080, 30 fps, 109 frames이며 audio/video start는 모두 0이고 전체 decode를 통과했다. `readability-sorted-v3-verification.json`에 panel/triptych hash, codec, frame count, 정렬 방식과 layout metadata를 기록했다.

이 historical run의 manifest는 `v2.3-regression`, `claire_v2.3.1`, 52000, baseline, artifact-only다. v3 결과로 재명명하거나 재사용하지 않는다.

새 기본값 변경 전 explicit v2.3 회귀 실행도 별도로 통과했다. 현재 동일 경로를 실행하려면 `--a2f-model v2.3-regression`을 반드시 붙인다.

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /home/aim/Downloads/test.wav \
  --a2f-model v2.3-regression \
  --name default-v23-readable-sync-final \
  --progress auto --capture-timeout 600 --mrq-timeout 600
```

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-144232-default-v23-readable-sync-final/
```

- runtime attestation: `v2.3-regression` ↔ `audio2face-3d-pretrained` ↔ `127.0.0.1:52000`
- content sync: 보정 전 +6 frames/+200 ms, 보정 후 0 frames/0 ms, correlation 0.818
- readable panel: H.264 640×540, 30 fps, 109 frames, 최소 16 px, curve 18 px, current effective 내림차순, emotion 표시 없음
- 최종 triptych: H.264/AAC 1920×1080, 109 frames, A/V start 0 ms, full decode PASS
- triptych SHA-256: `6c05a7ed62109545520728eafee9f34135556c2413cea5b659122ddb77ee9d94`

## 최종 v3.0 diffusion dynamic-safe showcase

제품 기본값 자체의 exact no-motion-config characterization은 다음 명령/run으로 통과했다.

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /home/aim/Downloads/test.wav \
  --avatar Taro --name default-v30
```

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-164026-default-v30-identity-r2/
```

manifest는 canonical-default/explicit=false/fallback=false, v3.0 diffusion, `multi_v3.2`, 52100, intensity-neutral baseline/final-render identity bake, 218→109 frames를 기록한다. 91개 recorded curve sample의 최대 오차는 `1.45e-7`이다. 이 native default triptych도 H.264/AAC 1920×1080, 109 frames, A/V 0 ms, full decode PASS이며 SHA-256은 `3534fe6dfe9a506970e411f518661fe1aa1c64c6737ad6ff43617c1bc71d5b3d`다.

최종 사용자 확인 대상은 다음 fresh no-option v3 run이다.

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /home/aim/Downloads/test.wav \
  --avatar Taro \
  --name default-v30 \
  --motion-config scripts/audio2face-metahuman/configs/motion-v3-dynamic-safe-final-v1.json \
  --progress auto --capture-timeout 600 --mrq-timeout 600
```

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-165227-v30-dynamic-final-r3/
```

- model selection: canonical default, explicit=false, fallback=false
- model/runtime: `v3.0-diffusion`, transformer-diffusion, `multi_v3.2`, 52100, Claire
- official model revision: `b74132732fd9a9d29b237bec193ded64c9745e91`
- source: 218 frames, 실제 timeCode 약 60.0007 fps → audio-time interpolation → 109 frames/30 fps
- raw/effective: finite, `[0,1]` 밖 0건, effective max `0.939989`, `>=0.999` 0건
- final-render bake: 별도 run-owned AnimSequence에 52 curve × 218 key 적용
- lineage: avatar/mannequin/panel/audio의 run/input/audio/model/architecture/NIM/curve SHA/fps/frame count 11필드 일치
- lip sync: 새 v3 측정 +5 frames/+166.667 ms → 0 frames/0 ms, JawOpen correlation `0.93605`
- mannequin composite `JawOpen + MouthFunnel`: lag 0 frames, correlation `0.95785`
- recorded AnimSequence: 7 frame × 13 mouth curves, 최대 오차 `4.84e-6` < tolerance `1e-4`
- output: H.264/AAC, 1920×1080, 30 fps, 109 frames, A/V start 0 ms, full decode PASS

최종 triptych:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-165227-v30-dynamic-final-r3/taro-a2f-v30-dynamic-final-r3-v30-diffusion-final-v30-diffusion-layout-v3-triptych.mp4
SHA-256: 4b52d90b8c87ebc03e473d263824a5cb4f8353bce0caf14a90cb19abcc2bd1fd
```

동기 keyframe contact sheet:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-165227-v30-dynamic-final-r3/retarget-audited-contact-sheet.png
```

master-clock frame map과 확장 동기 검증:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-165227-v30-dynamic-final-r3/taro-a2f-v30-dynamic-final-r3-v30-diffusion-final-v30-diffusion-layout-v3-frame-map.jsonl
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-165227-v30-dynamic-final-r3/sync-expanded-verification.json
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-165227-v30-dynamic-final-r3/retarget-layer-diagnosis.json
```

master clock 계산은 `target_time(i) = i / 30`초다. raw/effective와 mannequin/panel은 이 시각에서 실제 CSV timeCode를 선형 보간한다. avatar는 동일 시각과 비교해 측정된 render latency만큼 `source_frame = clamp(i + measured_lag)`로 한 번 보정한다. 세 video input은 합성 직전 `settb=AVTB,setpts=N/(30*TB)`로 같은 PTS를 부여하며 authoritative audio는 0초에서 시작한다.

### Claire reference와 MetaHuman retarget 형상 차이

첨부된 historical frame 83은 `RAW / ACE REINFERENCE`였으며 첫 official client CSV와 두 번째 ACE inference의 curve SHA 동일성이 증명되지 않았다. canonical v3는 이를 intensity-neutral identity final bake로 교체했다.

새 identity run `20260827-164026-default-v30-identity-r2`에서 frame 83의 NIM raw/effective/mannequin input/recorded AnimSequence는 다음처럼 일치했다.

| Curve | NIM/effective | Recorded AnimSequence | abs error |
| --- | ---: | ---: | ---: |
| JawOpen | 0.182750859 | 0.182750917 | 5.78e-8 |
| MouthClose | 0.265526592 | 0.265526536 | 5.54e-8 |
| MouthFunnel | 0.168563 | 동일 허용오차 내 | <1e-6 |
| MouthRollLower | 0.387650 | 동일 허용오차 내 | <1e-6 |

따라서 curve attenuation/drop/double-process 결함은 아니었다. 같은 frame의 fixed-ROI normalized opening은 Claire reference 약 `0.0286`, Taro 약 `0.0821`이었다. 이 차이는 NVIDIA Claire pre-retarget pose basis와 `mh_arkit_mapping_pose_A2F`/MetaHuman DNA rig의 캐릭터별 geometry response다. 임의 gain으로 맞추지 않는다.

설치 ACE 2.5가 최종 MetaHuman에 소비하는 것은 ARKit 52(`TongueOut` 포함)다. `TongueIn` 등 extended tongue 16개는 Claire reference에만 적용되므로 final-render Top Active Curves에서 제외하고 68-curve heat strip/JSON/CSV에는 보존한다. mannequin에는 `Claire reference geometry — pre-MetaHuman retarget`를 명시한다.

공식 asset audit:

- `Face_AnimBP` SHA `83b7f1f...`: `Apply ACE Face Animations`, MouthClose bypass, A2F pose reference
- `mh_arkit_mapping_pose_A2F` SHA `0b4e58c...`
- `mh_arkit_mapping_anim_A2F` SHA `6a795b9a...`
- NVIDIA 공식 변경 curve: BrowDownLeft/Right, BrowInnerUp, MouthClose, MouthRollLower
- final sequence Face animation track: 정확히 1개

NIM gRPC는 solver blendshape weight를 제공하고 direct diffusion skin/jaw/eye geometry를 노출하지 않는다. 공개 SDK geometry executor는 현재 host의 CUDA/TensorRT stack보다 높은 별도 환경이 필요하므로 direct-geometry pixel equivalence는 검증하지 않았고, 이 경계를 `retarget-layer-diagnosis.json`에 기록했다.

### 후속 elderly Asian cross-avatar / geometry SDK gate

직접 geometry SDK 비교의 선행 조건은 Taro와 별개의 고령 Asian 남성 1명과 여성 1명 모두에 동일한 v3 curve lineage를 적용하는 것이다.

- UE 5.6-5.8, `mhc_seo.mhpkg`, 143.52 MB
- `Asian`, `MetaHuman`, `Editable` 태그
- Fab Standard License, NoAI
- Personal Free, Professional 유료

후속 provenance 감사에서 Taro는 Bridge preassembled bundle이지만 Bridge UI import가 아니었던 것으로 확정됐다. 과거 에이전트가 기존 Bridge credential file 내용을 읽어 official MHC download API에 전달하고 zip을 직접 풀었다. 이 방식은 현재 credential 보호 규칙상 재사용하지 않는다. 또한 보존된 official Bridge preset catalog에는 ethnicity, gender, age 필드가 전혀 없다.

사용자는 2026-08-27에 외형 기반 선별을 명시적으로 허용했다. 공식 66-preset preview 전체를 검토해 `Keiji`(`k8ezkISA`)를 고령 Asian 남성 외형 후보, `Sook-ja`(`l01pkISw`)를 고령 Asian 여성 외형 후보로 선택했다. 이는 `visual_estimate_not_demographic_metadata`이며 Epic의 공식 demographic metadata가 아니다.

공식 Bridge를 격리된 UE 5.6 프로젝트에서 열고 사용자가 Epic Content License Agreement를 직접 승인했다. 이후 Cinematic Complete Keiji와 Sook-ja bundle을 공식 UI로 다운로드하고 KairosSample에 `--ignore-existing --omit-dir-times`로 신규 파일만 import했다. Keiji 212개, Sook-ja 187개가 추가됐고 기존 Taro/Jesse BP/DNA 해시는 유지됐다.

두 신규 MetaHuman은 Taro 성공 run의 동일 v3.0 diffusion inference와 effective curve SHA를 재사용해 E2E를 완료했다.

| Avatar | Final lag | JawOpen correlation | AnimSequence max error | 결과 |
|---|---:|---:|---:|---|
| Taro | 0 frame | 0.9360 | 4.83e-6 | PASS |
| Keiji | 0 frame | 0.9136 | 3.99e-6 | PASS |
| Sook-ja | 0 frame | 0.8870 | 4.86e-6 | PASS |

세 run은 curve SHA `8c7e24f2…f6b3`, input/audio SHA, `multi_v3.2`, endpoint 52100, 30 fps/109 frames가 모두 같다. optical response 차이는 curve drop이 아니라 캐릭터별 DNA/pose retarget response다. 인종·성별·연령 성능 일반화로 해석하지 않는다.

AI 사진→MetaHuman도 검토했다. 공식 UE 5.6 경로는 사진 자체가 아니라 texture/material이 있는 FBX/OBJ head mesh를 MetaHuman Identity에서 solve한 뒤 MetaHuman Character의 `Conform from Identity`와 Assembly를 수행한다. 현재 Linux 바이너리의 Identity tracker/solver, Character Editor 및 Default Editor Pipeline 모듈은 모두 `PlatformAllowList: Win64`라 이 서버에서 해당 solve/assembly는 실행할 수 없다. Windows UE 5.6에서 assembled asset을 만든 뒤 이 프로젝트로 migrate하는 경우에만 가능하다. Tripo3D/Meshy/Rodin/KeenTools는 별도 계정·가격·라이선스를 가진 비공식 3D 생성 단계이며 이 Win64 경계를 없애지 않는다.

상세 증거:

`/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/cross-avatar-phase-a/20260827-seo-acquisition-gate/phase-a-manual-action.json`

최신 two-avatar audit:

`/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/cross-avatar-phase-a/20260827-taro-route-two-avatar-audit/elderly-asian-two-avatar-candidate-audit.json`

현재 수동 단계:

`/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/cross-avatar-phase-a/20260827-taro-route-two-avatar-audit/phase-a-manual-action-content-license.json`

Phase A 최종 결과와 즉시 확인 파일:

- `.../20260827-taro-route-two-avatar-audit/phase-a-result.json`
- `.../three-avatar-benchmark/three-avatar-v30-retarget-comparison.mp4`
- `.../three-avatar-benchmark/three-avatar-contact-sheet.png`

Phase B geometry SDK sidecar는 CUDA 12.8.1 + TensorRT 10.13.3.9 + SDK commit `1ca0f025…`로 실제 실행까지 PASS했다. 공식 `trt_info.json` 기본 FP32/`tacticSharedMem=48 KiB`와 NIM 비교용 explicit FP16/GPU-solver profile을 분리했다. 218 frames의 direct skin 24,002 vertices, tongue 5,602 vertices, jaw transform, eyes rotation 및 68 solver weights를 저장했다. 사용자 승인으로 diffusion NIM만 일시 중지했으며 실행 후 동일 container/52100 `ONLINE`으로 복구했다. 상세 상태는 `.tools/audio2face3d/sdk-v3-geometry/phase-b-status.json`에 있다.

## 2026-08-28 공식 ACE node 기반 눈 반응 개선

68 curve post-bake 실험에서 mannequin의 눈은 닫혔지만 최종 MetaHuman 눈은 열린 채였다. 원인은 Take Recorder가 이미 만든 bone animation 위에 float curve만 추가해도 MetaHuman pose mapping이 다시 실행되지 않기 때문이다. 이 결과는 진단용으로 보존하지만 품질 성공으로 쓰지 않는다.

설치된 NVIDIA ACE 2.5 공식 소스의 `FAnimNode_ApplyACEAnimation::Evaluate_AnyThread`는 `BlendshapeMultipliers`와 `BlendshapeOffsets`를 source weight에 직접 적용한다. Kairos helper는 source asset을 수정하지 않고 PIE avatar의 이 공식 node struct만 reflection으로 설정한다.

- official node header SHA-256: `95f3adcff961a69b079d937d24063589383c0242630045b4e0259d46270cb3c3`
- official node implementation SHA-256: `418fa8035c314ca32966a0e75628fa90f0e180d6e26d3fcff6939ceba31fcc8b`
- helper는 `ace_blendshape_override_nodes >= 1`과 exact map SHA를 capture status에 기록한다.
- 일반 `raw-ace-reinference`는 계속 strict compositor에서 거부한다. 증명된 node 경로만 `ace-node-overrides` lineage로 허용한다.

권장 opt-in 실행:

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py \
  /home/aim/Downloads/test.wav \
  --avatar Sook-ja \
  --motion-config scripts/audio2face-metahuman/configs/motion-v3-ace-node-quality-v4.json \
  --shot close-up-front \
  --name sookja-v30-ace-node-quality
```

이번 서버에서는 fresh UE capture를 두 번만 시도했고 둘 다 알려진 `VulkanPipeline.cpp:1666`, `VkResult=-13`으로 종료했다. 무한 재시도하지 않았다. 대신 이미 ACE node 1개/동일 5개 map으로 capture와 MRQ가 성공한 v3 source run `20260828-001546-v30-ace-source-quality-v3-sookja-r2-fresh`를 strict recovery 도구로 재합성했다. 새 v4 request와 이 source의 official 218-frame curve JSON SHA는 모두 `67584a10…c4580`으로 정확히 같았다.

```bash
python3 scripts/audio2face-metahuman/recompose-a2f-showcase.py \
  .tools/audio2face3d/official-cli-runs/20260828-001546-v30-ace-source-quality-v3-sookja-r2-fresh \
  --avatar-video .tools/audio2face3d/official-cli-runs/20260828-001546-v30-ace-source-quality-v3-sookja-r2-fresh/a2f-sook-ja-v30-ace-source-quality-v3-sookja-r2-fresh-close-up-f.mp4 \
  --output-dir .tools/audio2face3d/quality-review/20260828-sookja-v30-ace-node-quality-v3-recomposed
```

검증 결과:

| 항목 | baseline | ACE node quality |
| --- | ---: | ---: |
| EyeBlinkLeft max | 0.0686 | 0.5488 |
| EyeBlinkRight max | 0.0678 | 0.5421 |
| eyes region range mean | 1.0× | 2.308× |
| upper saturation | 0 | 0 |
| avatar content lag | 0 frame | +5 frame → 0 frame 자동 보정 |
| corrected JawOpen correlation | 0.887 | 0.913 |

이는 blink/eye response가 더 명확해졌다는 curve와 frame 증거이며, 자연스러움 전체를 수치로 보증하는 점수는 아니다. mouth/jaw는 의도적으로 1.0×로 유지했고 `TongueOut=0`이라 혀 품질 향상은 주장하지 않는다.

즉시 확인 파일:

- triptych: `.tools/audio2face3d/quality-review/20260828-sookja-v30-ace-node-quality-v3-recomposed/sookja-v30-ace-node-quality-layout-v3-triptych.mp4`
- baseline A/B: `.tools/audio2face3d/quality-review/20260828-sookja-v30-ace-node-quality-v3-recomposed/sookja-v30-baseline-vs-ace-node-quality-ab.mp4`
- contact sheet: `.tools/audio2face3d/quality-review/20260828-sookja-v30-ace-node-quality-v3-recomposed/sookja-v30-ace-node-quality-contact-sheet.png`
- manifest: `.tools/audio2face3d/quality-review/20260828-sookja-v30-ace-node-quality-v3-recomposed/recomposition-manifest.json`
- A/B·metrics 통합 검증: `.tools/audio2face3d/quality-review/20260828-sookja-v30-ace-node-quality-v3-recomposed/quality-review.json`
