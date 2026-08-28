# Audio2Face CLI hands-on introduction figure contract

## One-sentence argument

사용자가 고른 음성과 아바타·카메라·감정 설정을 CLI에 전달하면 오디오 기반 얼굴 애니메이션, MetaHuman 렌더, 검증된 영상과 진단 산출물을 재사용 가능한 한 흐름으로 만들 수 있다.

## Why this is needed

GUI에서 NIM endpoint, MetaHuman, Take Recorder, MRQ, 오디오 mux를 각각 설정하면 동일 입력을 재현하기 어렵고 model·curve·avatar 결과가 섞일 수 있다. CLI는 model lineage, master clock, frame count, codec 및 A/V sync gate를 한 실행 manifest로 묶는다.

## Capability versus evidence

- Capability: v2.3/v3.0, arbitrary local MetaHuman, named/custom camera, face/emotion/motion config, inference/capture/render/finalize/resume.
- Analysed here: `/home/aim/Downloads/test.wav`, Taro/Keiji/Sook-ja, four named shots, custom front, baseline/dynamic/ACE-node configs.
- Validated evidence: v3 `multi_v3.2`, endpoint 52100, 218 raw curve samples, 109 output frames at 30 fps, H.264/AAC, A/V start delta 0 ms, full decode.
- Boundary: MetaHuman acquisition/assembly can require official Epic UI; Linux Vulkan can fail intermittently; extended tongue/head motion is not claimed as a completed ACE 2.5 feature.

## Figure A — concept overview

- Archetype: schematic-led composite.
- Reading path: audio + choices → audio-driven facial animation → selected MetaHuman capture → render → verified video + reusable artifacts.
- Exact title: `Audio to animated MetaHuman — one reusable CLI journey`
- Exact stage labels: `Audio + choices`, `Audio-driven face`, `Selected MetaHuman`, `Camera + render`, `Video + artifacts`.
- Configuration copy: `avatar · camera · emotion · motion`.
- Boundary copy: `No training · source assets preserved · repeatable run`.
- Prohibited in artwork: endpoint/port, GPU names, fixed sample/frame counts, fixed A/V result, test.wav-specific values.

## Figure B — runtime architecture

- Archetype: novice left-to-right service journey.
- Reading direction: strictly left → right, no feedback arrows or lane crossings.
- Exact title: `How the Audio2Face MetaHuman CLI works`
- Exact nodes: `1. Choose input`, `2. Generate face motion`, `3. Animate MetaHuman`, `4. Render video`, `5. Check results`.
- Plain-language subtitles: `audio · avatar · camera · emotion`, `NVIDIA Audio2Face`, `NVIDIA ACE + Unreal Engine`, `frames + original audio`, `video · report · diagnostics`.
- Boundary copy: `Setup may need VNC once · repeat runs use the CLI`.
- Internal terms such as NIM model IDs, ports, GPU model names, lineage, solver, MRQ and FFmpeg are forbidden in the artwork; they remain in body/reference text.

## Evidence ledger

| Display item | Source |
| --- | --- |
| v3.0 diffusion / multi_v3.2 / 52100 | successful v3 manifests and model registry |
| 218 raw samples / 109 frames / 30 fps | successful v3 manifests |
| H.264/AAC / A/V 0 ms / decode PASS | ffprobe and verification JSON |
| GPU1 A4500 inference / GPU0 Quadro render | runtime inventory and successful run manifests |
| FFmpeg 6.1.1 | project-local wrapper inventory |

## Prohibited implications

- NVIDIA CES demo와 픽셀 또는 perceptual quality가 동일하다고 주장하지 않는다.
- Claire mannequin을 선택 MetaHuman의 exact geometry라고 표시하지 않는다.
- extended tongue/head motion, Linux MetaHuman assembly 또는 fresh Vulkan capture를 항상 성공한다고 표시하지 않는다.
- GUI가 완전히 필요 없거나 모든 Epic 인증이 자동화된다고 표시하지 않는다.
