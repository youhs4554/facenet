# Audio2Face-3D v3 Geometry SDK Sidecar

## 목적

호스트 CUDA 12.0, driver, TensorRT, 전역 경로를 변경하지 않고 NVIDIA 공식 Audio2Face-3D SDK의 direct geometry 경로를 실행한다. 기존 NIM 2.0 컨테이너와 성공 run은 보존한다.

## 고정 버전

- Base: `nvidia/cuda:12.8.1-devel-ubuntu22.04@sha256:6617a625…`
- TensorRT CUDA-12 wheel: `10.13.3.9`
- TensorRT headers: tag `v10.13.3`, commit `94e2b9ef…`
- Audio2Face-3D SDK: commit `1ca0f025…`
- A2F model: `Audio2Face-3D-v3.0`, revision `b741327…`, Claire identity index 0
- GPU: physical GPU1 RTX A4500, container-visible device 0

공식 TensorRT 25.08 container는 TRT 10.13이지만 CUDA 13.0이라 SDK의 `<13` 범위를 벗어난다. 현재 NIM 2.0은 CUDA 12.8이지만 TRT 10.9다. 따라서 CUDA 12.8 official base와 CUDA-12 TensorRT 10.13 official wheel/header 조합을 사용한다.

## 보안·격리

- SDK/model/input은 read-only mount, `.tools/audio2face3d/sdk-v3-geometry`만 writable
- `read_only`, `no-new-privileges`, `cap_drop: ALL`, GPU1 device restriction
- token/credential/env secret를 image layer나 command에 전달하지 않음
- host `/usr/local/cuda`, driver, Python TensorRT, `ld.so.conf` 변경 없음
- existing NIM 자동 stop 금지
- Phase A의 두 역할, 실제 MP4/manifest, benchmark SHA, shared curve SHA를 통과해야만 runtime 시작
- 각 실행은 `/output/runs/<run-id>` 전용 디렉터리를 사용하며 ONNX/TRT-info/engine/TRT/GPU 옵션이 일치하지 않는 stale engine을 거부
- 성공·실패·VRAM 차단 모두 `EXIT` audit으로 UE PID와 기존 container ID/image/state/restart count를 전후 비교

## 명령

```bash
# build only; GPU inference 없음
scripts/audio2face-metahuman/sdk-v3-geometry/run-sidecar.sh build

# CUDA/TRT/SDK/exporter identity 확인
scripts/audio2face-metahuman/sdk-v3-geometry/run-sidecar.sh inspect

# VRAM gate 후 engine build + direct geometry + solver 비교
scripts/audio2face-metahuman/sdk-v3-geometry/run-sidecar.sh run
```

## 최종 실행 증거

- Image digest: `sha256:858ccca27566745a232f5a69beab32a76afb2f6ff83fcd43880eb54557b4dbf6`
- Image size: 8,547,406,631 bytes
- Container inspect: CUDA 12.8, TensorRT 10.13.3.9, SDK commit `1ca0f025…`, RTX A4500
- SDK `libaudio2x.so`: 79/79 build PASS
- exporter compile/`--help`: PASS
- build 전후 host global paths/containers: PASS, 변경 없음
- official `trt_info.json` effective options: FP32, `tacticSharedMem=49,152 bytes`(48 KiB), batch 1. 요청되지 않은 FP16/workspace override는 없음
- sidecar behavior tests: 23 PASS; 전체 Audio2Face tests: 158 PASS + 30 subtests
- Phase A runtime gate: Keiji/Sook-ja 두 role, 6개 run artifact, benchmark와 shared curve SHA 검증 PASS
- 실패 경로 host audit: 기존 UE PID 집합과 NIM container identity/state/restart count 변경 없음, PASS

사용자 승인 후 `audio2face-3d-diffusion`만 일시 중지하여 GPU1 free 17,366 MiB를 확보했고, engine build와 direct inference를 완료했다. `audio2face-3d-pretrained`는 계속 실행했다. 실행 종료 후 동일 diffusion container ID를 재시작했고 endpoint 52100 `ONLINE`, restart count 0, host/container identity audit PASS를 확인했다.

직접 결과:

- 218 timecoded frames, first/last `0.0 / 3.616625 s`
- skin `[218, 24002, 3]`, tongue `[218, 5602, 3]`
- jaw `[218, 16]`, eyes `[218, 6]`
- geometry/weights 모두 finite, timestamp strictly monotonic
- NIM 원본과 재실행 CSV: byte-identical, curve MAE `0.0`
- SDK GPU solver + 동일 face/request params + NIM FP16 비교 profile 대 NIM: 68-curve MAE `0.0124158`, RMSE `0.0342765`, timestamp max delta `0.0 s`
- 공식 FP32와 NIM-match FP16 SDK weights 차이: MAE `0.0001625`; FP16은 NIM 잔여 차이를 유의미하게 줄이지 않음
- direct skin geometry 대 52-pose solver reconstruction: mean Euclidean error `0.0770312` model-coordinate units. SDK 문서가 물리 단위를 명시하지 않으므로 mm/cm로 재명명하지 않음

NVIDIA는 독립 SDK/NIM 실행의 weight equality tolerance를 공개하지 않는다. 따라서 위 수치는 `measured`이며 임의 PASS threshold를 만들지 않았다. NIM asset hashes는 SDK model assets와 동일하지만 tongue solver offset 및 일부 mouth curves를 중심으로 runtime/pipeline 경계가 남는다.

주요 증거:

- `.tools/audio2face3d/sdk-v3-geometry/phase-b-status.json`
- `.tools/audio2face3d/sdk-v3-geometry/final-sdk-nim-benchmark.json`
- `.tools/audio2face3d/sdk-v3-geometry/runs/sdk-v30-20260827T135357Z-nim-fp16-gpu-solver/verification.json`
- `.tools/audio2face3d/sdk-v3-geometry/authorized-runtime/sdk-v30-20260827T135357Z-nim-fp16-gpu-solver/host-restoration-audit.json`
- `.tools/audio2face3d/sdk-v3-geometry/runs/sdk-v30-20260827T135357Z-nim-fp16-gpu-solver/direct-geometry-visualization/direct-sdk-claire-geometry-reference.mp4`
- `.tools/audio2face3d/sdk-v3-geometry/runs/sdk-v30-20260827T135357Z-nim-fp16-gpu-solver/direct-geometry-visualization/direct-sdk-geometry-contact-sheet.png`

Direct geometry 영상은 official `skinGeometry` vertex positions를 사용한다. 화면의 삼각형은 official `frontalMask` 위에 만든 로컬 2D Delaunay 표시 topology이며 NVIDIA의 원본 triangle topology라고 주장하지 않는다. contact sheet의 source frames 166/172는 30fps avatar frames 83/86의 `2.7666/2.8666 s`와 대응한다.

디스크 사용량은 sidecar evidence 전체 약 5.8 GiB, 최종 NIM-match run 약 1.3 GiB, Docker image 8,547,406,631 bytes다. 현재 여유 공간은 약 274 GiB다. 산출물을 보존하기 위해 cleanup은 실행하지 않았다. 향후 사용자가 명시적으로 정리할 때만 최종 run 경로를 확인한 뒤 제거하고, image는 `docker image rm a2f-v3-geometry-sdk:cuda12.8-trt10.13`로 별도 정리한다.

## 공식 근거

- NVIDIA Audio2Face-3D SDK: <https://github.com/NVIDIA/Audio2Face-3D-SDK/tree/1ca0f02535ed774f5dbcd724a31cd486368dc783>
- NVIDIA TensorRT source: <https://github.com/NVIDIA/TensorRT/tree/94e2b9ef6d2cce74c76cdad499cca36cc4949197>
- NVIDIA Audio2Face-3D hub: <https://github.com/NVIDIA/Audio2Face-3D>
- NVIDIA NGC A2F model: <https://catalog.ngc.nvidia.com/orgs/nim/nvidia/models/audio2face_3d_model>
