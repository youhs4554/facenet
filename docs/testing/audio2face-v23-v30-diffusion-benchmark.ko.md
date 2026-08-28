# Audio2Face-3D v2.3 regression ↔ v3.0 diffusion 품질·통합 검증

작성일: 2026-08-27
상태: v3.0 diffusion canonical 기본, v2.3 explicit 호환, dynamic-safe/lineage/master-clock 검증 완료

## 결론

NVIDIA CES 2025 영상의 개선은 단순 curve gain이 아니라 `multi_v3.2` diffusion 모델에서 발생한다. 현재 서버에서는 기존 `claire_v2.3.1` regression을 52000 포트에 그대로 유지하고, 공식 NIM 2.0 `multi_v3.2` FP16 diffusion을 52100 포트에 별도 설치했다.

동일 `/home/aim/Downloads/test.wav`, Taro, 정면 카메라, 30 fps MRQ 조건에서 v3는 v2보다 jaw와 eye motion range가 각각 약 2.11배, 2.24배였고 mouth range는 약 1.11배였다. 반면 brow range는 약 0.53배였고 cheek temporal jerk는 약 2.78배였다. 따라서 v3가 더 역동적인 것은 입증됐지만, 모든 영역에서 인간 지각상 더 자연스럽다고 수치만으로 단정하지 않는다.

2026-08-27 제품 결정에 따라 canonical 기본값은 `v3.0-diffusion`이다. v3가 unavailable이면 v2로 자동 fallback하지 않는다. legacy v2는 `--a2f-model v2.3-regression`으로 계속 지원한다. UE Linux/Vulkan 별도 Editor 시작 SIGSEGV는 bounded failure로 처리하며 model을 조용히 바꾸지 않는다.

## 공식 목표 영상

- URL: <https://www.youtube.com/watch?v=dm8-gNin76c>
- 제목: `NVIDIA ACE | New Audio-Driven AI Facial Animation Features Coming to NVIDIA Audio2Face`
- 채널/게시일: NVIDIA Game Developer, 2025-01-08
- 로컬 파일: `.tools/audio2face3d/reference/nvidia-ces2025-diffusion/nvidia-a2f-ces2025-diffusion.mp4`
- SHA-256: `d6a9507d58f1ef8d67b755b63dd17ffc420b18b5f217ffea7c2c7589c93594a2`
- stream: H.264 1920×1080, 30 fps, 635 frames, 약 21.17초; AAC 포함
- timecoded contact sheet: `.tools/audio2face3d/reference/nvidia-ces2025-diffusion/contact-sheet-timecoded.png`
- machine-readable target: `.ecc/benchmarks/audio2face-v23-v30/20260827-test-wav/quality-target.json`

관찰 기준:

| 구간 | 관찰 가능한 목표 |
| --- | --- |
| 0.0–1.0초 | 입술 초근접에서 closure, roll, funnel과 치아 사이 aperture의 세부 변화 |
| 1.5–6.5초 | 큰 jaw opening, smile/cheek, eyebrow와 eye-wide가 음성에 맞춰 함께 변화 |
| 7.0–10.0초 | brow-down/눈 주변 긴장과 강한 mouth shape가 감정 전환 중 유지 |
| 10.5–13.5초 | rounded lip, jaw, brow/eye가 서로 독립적으로 움직이며 과도한 떨림이 없음 |
| 14.0–16.5초 | 3/4 시점에서 eye direction, blink/squint, cheek와 mouth asymmetry 확인 가능 |

공식 영상은 Taro가 아니며 오디오, identity, direct geometry/solver 선택, renderer, lighting, camera edit가 다르다. 따라서 픽셀 또는 curve 수치의 직접 동등성을 주장하지 않는다.

## 공식 버전과 라이선스 고정

| 구성 | 고정값 |
| --- | --- |
| Audio2Face-3D 허브 | commit `4d61b6b81ad7b5108512ea0eab10d8712ea4a236` |
| Audio2Face-3D SDK | commit `1ca0f02535ed774f5dbcd724a31cd486368dc783`, MIT |
| Training Framework | commit `112c5eb3408afd065ac8974b2c6ea9ab0e3965c6`, Apache-2.0 |
| v3 open model | HF revision `b74132732fd9a9d29b237bec193ded64c9745e91` |
| v3 model license | NVIDIA Open Model License |
| NIM | `2.0.0-rc8`, image digest `sha256:6112996e0cbfd7a09d8555712bf3d03142da7bed6cade8cddcf0a6308312df71` |
| ACE Unreal plugin | `2.5.0-20250614-2282` |
| Unreal Engine | 5.6.0, changelist 43139311 |

공식 1차 자료:

- <https://github.com/NVIDIA/Audio2Face-3D>
- <https://github.com/NVIDIA/Audio2Face-3D-SDK>
- <https://github.com/NVIDIA/Audio2Face-3D-Training-Framework>
- <https://huggingface.co/nvidia/Audio2Face-3D-v3.0/tree/b74132732fd9a9d29b237bec193ded64c9745e91>
- <https://docs.nvidia.com/ace/audio2face-3d-microservice/latest/text/support-matrix.html>
- <https://docs.nvidia.com/ace/audio2face-3d-microservice/2.0/text/deployment/container-config.html>
- <https://docs.nvidia.com/ace/ace-unreal-plugin/latest/ace-unreal-plugin-animation.html>
- <https://developer.nvidia.com/blog/nvidia-open-sources-audio2face-animation-model/>

## 모델·runtime 구조

지원 경로 판정:

| 경로 | 현재 호스트 판정 | 근거 |
| --- | --- | --- |
| ACE 2.5 RemoteA2F → NIM 2.0 regression | 지원/explicit legacy | Linux plugin과 52000 서비스 실제 검증 |
| ACE 2.5 RemoteA2F → NIM 2.0 diffusion | 지원/구현 | NIM 2.0 공식 `multi_v3.2`, 52100 실제 검증 |
| ACE UE on-device local model | 현재 Linux 불가 | 설치 plugin의 `A2FLocal`과 Models plugin은 Win64 경로 |
| Audio2Face-3D SDK offline | 공식 fallback | SDK는 CUDA `>=12.8,<13`, TensorRT `>=10.13,<11`; 현재 host stack 12.0/10.9와 불일치하므로 별도 container 필요 |
| Training Framework Python inference | 연구/offline 가능 | UE RemoteA2F production 경로가 아니며 새 학습은 수행하지 않음 |

공식 허브는 Audio2Emotion v2.2를 production, v3.0을 experimental open-model 항목으로 표시하지만 두 repository는 현재 `hossay` 계정에서 gated access 승인이 없어 다운로드하지 않았다. 현재 NIM 2.0 profile이 실제 사용한 것은 `a2e_v2.1_a10g_fp32_bs38_v5`이며 manifest와 engine hash에 이 차이를 기록했다. 접근 조건을 우회하거나 다른 emotion 모델로 위장하지 않았다.

### v2.3 baseline

- container: `audio2face-3d-pretrained`
- endpoint: `127.0.0.1:52000`
- model: `claire_v2.3.1`, regression
- GPU: RTX A4500 device 1
- 기존 cache/map/run은 변경하거나 삭제하지 않았다.

### v3.0 diffusion

- container: `audio2face-3d-diffusion`
- endpoint: `127.0.0.1:52100`
- NIM model ID: `multi_v3.2`
- identity: `claire`, `constant_noise: true`
- A2F engine: 공식 NGC `multi_v3.2_a10g_fp16_bs38_v5`
- A2F engine SHA-256: `5bcefb513c9ef858ea55c7847814e1a37cef93e68190f9fa17471be96c193cd4`
- A2E engine: 컨테이너의 동일 공식 A2E ONNX를 RTX A4500 single-stream shape로 TensorRT 변환
- A2E engine SHA-256: `2d0de12b36fd17aa8b571a6ce707e996f737a0e7bf3012a3e4491f5b2185a6a6`
- config: `.tools/audio2face3d/v3/nim-custom-configs/`

RTX A4500은 Ampere/compute capability 8.6이며 NVIDIA 문서의 RTX 30 fallback이 A10G profile을 사용한다. A10G pre-generated A2F/A2E 엔진을 둘 다 그대로 쓰면 기존 v2와 동시 실행 시 A2E context의 약 2.9GB 추가 요청에서 OOM이 발생했다. 공식 문서의 custom-entrypoint를 사용해 A2F FP16 가중치/엔진은 그대로 두고 A2E의 최대 동시 batch만 1로 줄였다. 이 변경은 얼굴 모델·가중치·precision을 바꾸지 않는다.

v3 NIM 실행 로그에서 다음을 확인했다.

```text
n_tracks = 1
use_gpu_solver = 1
inference_type = diffusion
model identity = claire, 0
Running... 0.0.0.0:52000
```

v3 원 모델은 프레임마다 skin 72,006, tongue 16,806, jaw 15, eyes 4 scalars의 geometry motion을 생성한다. NIM의 GPU solver가 이를 MetaHuman에 전달할 52 face + 16 extended tongue = 68 blendshape로 변환한다. 따라서 direct geometry의 세부 정보 일부는 solver/ARKit/MetaHuman retarget 단계에서 손실될 수 있다.

## MetaHuman ACE mapping 감사

실제 프로젝트 파일의 문자열/asset reference와 SHA를 검사했다.

Machine-readable audit: `.ecc/benchmarks/audio2face-v23-v30/20260827-test-wav/metahuman-mapping-audit.json`

| 항목 | 결과 |
| --- | --- |
| `Apply ACE Face Animations` | `Face_AnimBP.uasset`에 `AnimGraphNode_ApplyACEAnimation` 존재 |
| MouthClose conflict | `Bypass MH MouthClose`와 `AnimGraphNode_ModifyCurve` 존재 |
| NVIDIA pose | `/NV_ACE_Reference/mh_arkit_mapping_pose_A2F` 참조 존재 |
| Face_AnimBP SHA | `83b7f1f26934e0de77741f4645b97851597f61b9a50b3108df9a1798568d26f8` |
| A2F pose SHA | `0b4e58c129f5e01633cf4f670e84788f76bea090107a54ad7545ff6111c832e0` |
| A2F anim SHA | `6a795b9a4616f06f2c0390361ccfa8d5e24457a72ca8fab60049464cf37374a5` |

공식 가이드가 변경한 BrowDownLeft/Right, BrowInnerUp, MouthClose, MouthRollLower mapping을 사용하는 상태다. 이 감사 결과로 mapping 누락은 현재 quality gap의 1차 원인에서 제외했다.

## 데이터·시각화 산출물 계약

CLI는 모든 inference에서 다음을 생성한다.

```text
motion-artifacts/
  blendshapes.raw.json
  blendshapes.raw.csv
  blendshapes.effective.json
  blendshapes.effective.csv
  emotion.input.json
  emotion.input.csv
  emotion.smoothed.json
  emotion.smoothed.csv
  effective-motion-config.json
  motion-comparison-metrics.json
  blendshape-visualization.mp4
  artifact-manifest.json
```

- raw 68 curve와 10 emotion은 원본 frame/timecode와 함께 보존한다.
- v3 NIM은 약 60 fps로 218 frames를 반환했다. 원본 JSON/CSV는 218 frames 그대로 보존하고, visualization만 `linear-timecode`로 30 fps 109 frames에 resample한다.
- JSON config는 schema version, finite/range, 알 수 없는 key, curve/region 이름, emotion time ordering을 strict 검증한다.
- 최종 avatar+visualization hstack은 avatar AAC를 한 번만 보존하며 정확히 같은 109 frames를 사용한다.

## 동일 조건 정량 A/B

정량 보고서:

```text
/home/aim/workspace/hosang/repo/facenet/.ecc/benchmarks/audio2face-v23-v30/20260827-test-wav/metrics.json
```

| 영역 | v2.3 range mean | v3.0 range mean | v3/v2 | v2 jerk | v3 jerk |
| --- | ---: | ---: | ---: | ---: | ---: |
| jaw | 0.049713 | 0.105068 | 2.114 | 3.766 | 4.674 |
| mouth | 0.169065 | 0.188230 | 1.113 | 5.834 | 7.619 |
| brows | 0.240361 | 0.128474 | 0.535 | 1.684 | 1.915 |
| cheeks/nose | 0.098441 | 0.076061 | 0.773 | 0.518 | 1.438 |
| eyes | 0.013207 | 0.029598 | 2.241 | 0.528 | 0.511 |
| tongue | 0.049652 | 0.060180 | 1.212 | 2.976 | 2.114 |

모든 v2/v3 raw curve 값은 finite였고 `[0, 1]` 밖 값 비율은 0이었다. 공식 client wall time은 v2 1.92초, v3 3.07초였다. 이 시간은 process 시작, gRPC, rate limiting, CSV/WAV 저장까지 포함하며 순수 GPU kernel latency가 아니다.

안전한 expressive config는 v3 default 대비 jaw 1.12배, mouth 1.14배, brows 1.59배, cheeks 1.30배, eyes 1.28배의 range를 냈고 out-of-range/clipping은 없었다. 다만 jerk도 증가했으므로 default보다 더 자연스럽다는 표현은 사용하지 않는다.

## 실제 영상 증거

v3 성공 run:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-130419-test-wav-v30-diffusion-taro-r2/
```

- avatar MP4: `taro-a2f-test-wav-v30-diffusion-taro-r2-final.mp4`
- SHA-256: `f3458ea90c69a10041eed268476e4adf82a3b40ceab8017992a84e411602866d`
- H.264 1920×1080, 30 fps, 109 frames, 3.633333초
- AAC 48 kHz mono, 3.626초, A/V start delta 0 ms, full decode PASS
- Take Recorder mouth candidates 24개, `JawOpen` recorded range `0.764211`
- clothed Taro, original face/hair/groom/eyes/teeth 유지

avatar+blendshape 비교:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/official-cli-runs/20260827-130419-test-wav-v30-diffusion-taro-r2/taro-a2f-test-wav-v30-diffusion-taro-r2-final-blendshape-comparison-fixed.mp4
```

- H.264 2880×1080, AAC 48 kHz mono, 109 frames, A/V start 0 ms, decode PASS
- SHA-256: `d9ed85cf9a2e5aeaae690ccff5b4cda431f6a3acebf2510f02c0b6a14c34b0fa`

v2/v3 Taro A/B:

```text
/home/aim/workspace/hosang/repo/facenet/.ecc/benchmarks/audio2face-v23-v30/20260827-test-wav/v23-v30-taro-avatar-hstack.mp4
```

- H.264 3840×1080, AAC 48 kHz mono, 109 frames, A/V start 0 ms, decode PASS
- SHA-256: `5df692872af6b91c90f28361d12b634bdea96264ca1ffa4b6c6fc10017684158`
- contact sheet: `.ecc/benchmarks/audio2face-v23-v30/20260827-test-wav/avatar-contact-sheet.png`

## 실행 명령

v3 서비스를 재기동하거나 health를 확인한다.

```bash
scripts/audio2face-metahuman/start-a2f-v3-diffusion.sh
```

canonical 기본 v3.0 diffusion:

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /home/aim/Downloads/test.wav \
  --name default-v30
```

explicit legacy v2.3:

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /home/aim/Downloads/test.wav \
  --a2f-model v2.3-regression \
  --name legacy-v23
```

검증된 dynamic-safe final-render:

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py /home/aim/Downloads/test.wav \
  --motion-config scripts/audio2face-metahuman/configs/motion-v3-dynamic-safe-final-v1.json \
  --name default-v30
```

## 최신 v2 ↔ v3 default ↔ v3 dynamic-safe benchmark

Machine-readable report:

```text
/home/aim/workspace/hosang/repo/facenet/.ecc/benchmarks/audio2face-v23-v30/20260827-default-v3-dynamic-lineage/benchmark.json
SHA-256: 5cdffe844993bc9576d3ab154f9df1bcdc4a60ede42f717948585fa99cbb46cd
```

동일 `/home/aim/Downloads/test.wav` 비교:

| 비교 | jaw range | mouth | brows | cheeks | eyes |
| --- | ---: | ---: | ---: | ---: | ---: |
| v3 default raw / v2.3 raw | 2.114× | 1.113× | 0.535× | 0.773× | 2.241× |
| v3 dynamic request raw / v3 default raw | 1.410× | 1.521× | 2.249× | 2.354× | 1.589× |
| v3 dynamic final / v3 default raw | 1.699× | 1.628× | 2.681× | 2.583× | 1.836× |

v3 dynamic final은 finite이고 전체 14,824개 값이 `[0,1]` 안에 있으며 최대 `0.939989`, `>=0.999` 0건이다. 다만 temporal derivative도 증가했다. 특히 dynamic request의 cheek jerk는 v3 default의 약 3.03배였으므로 “더 역동적”은 입증하지만 “더 자연스럽다”를 수치만으로 주장하지 않는다.

최종 dynamic run은 `20260827-165227-v30-dynamic-final-r3`이다. no-option model selection이 v3/52100을 선택했고 218 raw frames를 109 frame으로 timecode resample했으며, exact curve bake/retarget audit/final triptych lineage와 full decode가 통과했다.

## LAM 판정

`LAM: Large Avatar Model for One-shot Animatable Gaussian Head`는 NVIDIA A2F의 audio backbone이 아니다. 본 모델은 한 장의 이미지에서 FLAME 기반 animatable Gaussian head를 재구성한다.

- 논문: <https://arxiv.org/abs/2502.17796>
- 공식 repo: <https://github.com/aigc3d/LAM>, commit `339573649dd93df4cba8093a964e85a80d1b61f3`
- 별도 공식 LAM-Audio2Expression repo: <https://github.com/aigc3d/LAM_Audio2Expression>, commit `02a703c3ea7d8e360eb43098eca85ee98a083529`
- weights: `3DAIGC/LAM_audio2exp`, revision `0fe5f4dbb283ec7d9c01688681e6e4b6ac314858`, 406.2MB, Apache-2.0

LAM-A2E는 Wav2Vec encoder로 52 ARKit curve를 생성할 수 있지만 v3 diffusion의 direct skin/tongue/jaw/eyes geometry나 NVIDIA ACE/NIM production path를 제공하지 않는다. 특히 LAM 논문 자체가 FLAME에는 tongue blendshape가 없다고 명시한다. 따라서 이 파이프라인의 품질 향상 모델로 허위 통합하지 않았다. `a2f_lam_adapter.py`는 52개 공통 curve를 reference artifact로 변환하고 16개 extended tongue curve를 `unavailable`로 명시하는 격리 어댑터만 제공한다.

## 남은 한계

- NVIDIA CES 영상과 Taro의 avatar/audio/renderer/direct-geometry 조건이 달라 수치 동등성을 주장할 수 없다.
- NIM UE 경로는 68 blendshape solver 출력이므로 v3 direct geometry의 skin/jaw/tongue/eye 정보 일부가 손실된다.
- `--motion-config`의 face parameters와 constant emotion strength는 ACE WAV 호출에 적용된다. ACE 2.5 WAV API가 직접 노출하지 않는 per-curve gain/bias/clamp, attack/release와 timecoded emotion은 `curve_application=final_render`일 때 run-owned captured AnimSequence 복제본의 52개 지원 curve에 bulk bake한다. `artifact_only`이면 raw/effective artifact와 시각화만 바꾼다.
- r2 성공 이후 r3/r4에서 A2F 호출 전 별도 UnrealEditor 시작 중 Linux/Vulkan SIGSEGV가 2회 재현됐다. 기존 사용자 UE, v2/v3 NIM, 성공 산출물은 유지했고 드라이버 변경이나 재부팅은 수행하지 않았다.

## ECC 적용

- `ecc:orch-change-feature`: 기존 동작 보존과 변경 gate 관리
- `ecc:research-ops`: NVIDIA/논문/공식 repo/model card와 revision/license 검증
- `diagnose`: NGC 인증, A2E context OOM, UE API naming, FFmpeg frame truncation을 원인별 분리
- `ecc:tdd-workflow`: schema/config/model registry/resampling/visualization/benchmark 테스트를 RED→GREEN으로 구현
- `ecc:benchmark`: v2.3↔v3.0과 v3 default↔expressive-safe 동일 입력 비교
- `ecc:verification-loop`: unit regression, ffprobe, full decode, contact sheet, manifest/hash gate 수행
