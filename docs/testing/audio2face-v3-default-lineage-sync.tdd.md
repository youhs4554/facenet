# Audio2Face v3 default · lineage · master-clock TDD evidence

작성일: 2026-08-27

## 사용자 여정

- 모델 옵션을 생략한 사용자는 실제 v3.0 diffusion 결과를 받는다.
- 기존 v2 사용자는 explicit model 또는 기존 v2 resume로 계속 실행한다.
- 사용자는 v2 avatar와 v3 curve/mannequin이 섞인 MP4를 성공 결과로 받을 수 없다.
- triptych의 avatar, mannequin, Active Curves는 같은 source-audio master clock을 표시한다.

## RED → GREEN

| 보장 | RED | GREEN |
| --- | --- | --- |
| v2 avatar + v3 motion 거부 | `a2f_lineage.py` 없음으로 4 errors | 11-field compositor lineage가 mismatch를 `LineageError`로 거부 |
| no-option v3 default | parser/registry assertion 6 failures | default `v3.0-diffusion`, endpoint 52100 |
| old v2 resume 상속 | resume model-selection API 없음 | omitted model은 source v2/52000 상속, explicit mismatch 거부 |
| v2 relabel 방지 | cadence API 없음 | v3는 약 60 fps/218 frames, v2는 30 fps/109 frames 강제 |
| 1.000s impulse mapping | resampled frame에 source mapping 없음 | actual timeCode interpolation으로 frame 30 정확히 1.0 |
| panel bar/current frame | bar pixel metadata 없음 | current effective 값과 `int(width*value)` 일치 |
| mannequin/current frame | explicit impulse test 없음 | frame 30 geometry만 deformation |
| Claire basis mouth reconstruction | combined shape guarantee 없음 | neutral + JawOpen + MouthClose가 official delta의 정확한 선형합과 1e-6 내 일치 |
| unified PTS | `PTS-STARTPTS`만 사용 | 세 video input 모두 `settb=AVTB,setpts=N/(30*TB)` |
| debug mapping | frame map API 없음 | 109-line JSONL에 output/PTS/audio/curve/panel/mannequin/avatar/top curves 기록 |

## 실제 E2E

Native default exact command:

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /home/aim/Downloads/test.wav \
  --avatar Taro --name default-v30
```

historical `20260827-162354-default-v30`의 artifact-only curve SHA self-attestation은 최종 gate에서 기각했다. 수정된 native default run `20260827-164026-default-v30-identity-r2`는 intensity-neutral baseline/final-render identity bake로 v3/52100, 218→109, exact curve preservation, lineage, master frame-map, H.264/AAC/full decode를 통과했다.

## 2026-08-28 ACE node override regression gate

추가 품질 감사에서 post-capture float-curve bake가 이미 bake된 MetaHuman bone pose를 다시 평가하지 않는다는 결함을 재현했다. 따라서 일반 `raw-ace-reinference`는 계속 strict composition을 거부하며, 다음 조건을 모두 만족하는 경우만 별도 `ace-node-overrides` source identity를 허용한다.

1. motion config에 ACE 2.5 source 52 안의 multiplier/offset만 존재한다.
2. capture status의 `ace_blendshape_override_nodes >= 1`이다.
3. capture status의 runtime map이 effective config와 exact equality를 만족한다.
4. official client curve JSON SHA/model/input/audio/endpoint/fps/frame count lineage가 avatar/mannequin/panel/audio에서 같다.
5. post-render JawOpen content correlation이 ±1 frame 안에서 aligned다.

RED test는 증명 없는 raw re-inference와 node-count 0/map mismatch를 거부했다. GREEN test는 official node evidence가 있는 lineage만 허용하며 기존 v2/v3 mixed-lineage rejection을 유지한다. fallback recomposition은 source run을 수정하지 않고 별도 output에 pre-sync와 corrected MP4를 모두 보존한다.

- source capture: `20260828-001546-v30-ace-source-quality-v3-sookja-r2-fresh`
- before: +5 frames/+166.667 ms, correlation 0.9194
- after: 0 frames/0 ms, correlation 0.9134
- triptych: H.264/AAC, 1920×1080, 30 fps, 109 frames, A/V 0 ms, full decode PASS
- evidence: `.tools/audio2face3d/quality-review/20260828-sookja-v30-ace-node-quality-v3-recomposed/recomposition-manifest.json`

명령:

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /home/aim/Downloads/test.wav \
  --avatar Taro --name default-v30 \
  --motion-config scripts/audio2face-metahuman/configs/motion-v3-dynamic-safe-final-v1.json \
  --progress auto --capture-timeout 600 --mrq-timeout 600
```

run:

```text
.tools/audio2face3d/official-cli-runs/20260827-165227-v30-dynamic-final-r3/
```

- canonical default → v3.0 diffusion, `multi_v3.2`, 52100, fallback false
- official raw 218 frames, inferred 60.0007 fps → output 109 frames/30 fps
- effective range `[0, 0.939989]`, finite, outside 0, upper saturation 0
- ACE capture 52100, 218 animation samples, effective 52-curve final bake
- avatar content sync +5→0 frames, correlation 0.93605
- mannequin composite mouth signal lag 0, correlation 0.95785
- recorded curve preservation: 91 comparisons, max error 4.84e-6
- triptych H.264/AAC 1920×1080, 109 frames, start 0 ms, full decode PASS
- compositor lineage 4 components × 11 fields PASS
- actual resume smoke: `20260827-160552-resume-old-v23-inherits-source` → v2/52000, `20260827-162747-resume-v30-inherits-source` → v3/52100
- explicit v3 + old v2 resume는 `resume_model` exit 10으로 거부

## 산출물

- `manifest.json`
- `taro-a2f-v30-dynamic-final-r3-v30-diffusion-final-v30-diffusion-layout-v3-triptych.mp4`
- `taro-a2f-v30-dynamic-final-r3-v30-diffusion-final-v30-diffusion-layout-v3-frame-map.jsonl`
- `sync-expanded-verification.json`
- `v30-diffusion-sync-keyframes-contact-sheet.png`
- `retarget-layer-diagnosis.{json,csv}`
- `.ecc/benchmarks/audio2face-v23-v30/20260827-default-v3-dynamic-lineage/benchmark.json`

## 해석 경계

JawOpen은 fixed-camera rendered motion의 primary sync gate다. MouthClose/MouthFunnel/brow/eye의 full-frame PCA는 feature-specific ROI가 아니어서 낮은 상관은 `inconclusive`로 남긴다. Motion range와 jerk는 자연스러움 점수가 아니다.
