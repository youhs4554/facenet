# NVIDIA Audio2Face-3D × 공식 Taro MetaHuman 데모 사용 설명서

작성일: 2026-08-26
상태: **학습 없이 실행·녹화·MP4 검증 완료**

> 이 문서의 기존 VNC GUI 세션은 Claire v2.3.1/52000 역사적 데모입니다. canonical CLI의 신규 기본은 `multi_v3.2` diffusion/52100이며 v2.3은 explicit opt-in입니다. 상세 명령과 A/B 결과는 `docs/audio2face-metahuman-cli.ko.md`와 `docs/testing/audio2face-v23-v30-diffusion-benchmark.ko.md`를 확인하세요.

## 1. 무엇이 준비되어 있나요?

이 서버에는 Epic 공식 아시아인 남성 MetaHuman 프리셋 `Taro`와 NVIDIA 공식 pretrained Audio2Face-3D 런타임을 연결한 얼굴 중심 데모가 준비되어 있습니다.

```text
/home/aim/Downloads/video2.wav
  → Audio2Face-3D NIM 2.0 / Claire v2.3.1 pretrained
  → gRPC 127.0.0.1:52000
  → UE 5.6 / NVIDIA ACE 2.5 RemoteA2F
  → BP_Taro 얼굴·입·턱·눈썹·표정 애니메이션
```

학습, 파인튜닝, Claire Training Framework 전처리는 실행하지 않습니다.

원본 2023 시연은 Omniverse Audio2Face 앱이 Live Link로 얼굴 blendshape와 오디오를 UE MetaHuman에 보냈습니다. 이 서버에서는 현재 NVIDIA가 제공하는 Linux 경로인 Audio2Face-3D NIM + ACE 2.5 RemoteA2F를 사용합니다. 즉, 보이는 결과는 같지만 전송 계층은 legacy `NVIDIA Omniverse LiveLink`가 아니라 gRPC 기반 ACE입니다.

## 2. 최종 구성

| 항목 | 값 |
| --- | --- |
| Unreal Engine | 5.6.0, build 43139311 |
| NVIDIA ACE UE plugin | 2.5.0-20250614-2282 |
| Audio2Face runtime | NIM 2.0, Claire v2.3.1 pretrained |
| MetaHuman | Epic 공식 Cinematic `Taro`, MetaHuman 4.1.2 |
| UE 맵 | `/Game/Maps/TaroA2F/TaroFaceBodyDemo` |
| 얼굴 애니메이션 | `/Game/MetaHumans/Common/Face/Face_AnimBP` |
| Actor | `/Game/MetaHumans/Taro/BP_Taro` |
| 입력 WAV | `/home/aim/Downloads/video2.wav` |
| 입력 WAV 사양 | PCM s16le, 44.1 kHz, stereo, 10.0078초 |
| NIM GPU | NVIDIA RTX A4500 20 GB, 컨테이너 device 1 |
| UE 렌더 GPU | Quadro RTX 5000, Vulkan adapter 0 |
| VNC | DISPLAY `:1`, XAUTHORITY `/home/aim/.Xauthority` |
| noVNC | `http://100.113.15.83:6080` |
| NIM health | `http://127.0.0.1:8000/v1/health/ready` |
| NIM gRPC | `127.0.0.1:52000` |

## 3. 아바타와 상의 구성

최종 화면은 다음을 포함합니다.

- 원본 `Taro_FaceMesh`, 얼굴 material, 눈, 치아
- 원본 Hair, Eyebrows, Fuzz, Eyelashes, Mustache, Beard groom와 binding
- 원본 Body
- 원본 Cinematic hoodie skeletal mesh
- 얼굴 중심 bust 구도에서 보이는 목·어깨·가슴 상의

원본 MetaHuman Blueprint, hoodie mesh, 원본 material은 수정하지 않았습니다.

Linux UE 5.6 Vulkan에서 MetaHuman 공용 fabric material parent가 `VkResult=-13`을 일으킨 기존 재현 결과 때문에, 복제 데모 맵의 `Torso` 컴포넌트에만 `/Game/Audio2FaceDemo/Materials/M_TaroTop_VulkanSafe`를 덮어썼습니다. 색은 원본 후드와 비슷한 무난한 불투명 남색입니다.

## 4. 지금 바로 시연하기

현재 noVNC 화면에는 Taro 데모가 이미 열려 있고 `Local File` 입력도 설정되어 있습니다. 사용자가 할 일은 초록색 재생 버튼을 한 번 누르는 것뿐입니다.

1. 브라우저에서 `http://100.113.15.83:6080`을 엽니다.
2. `KairosSample Preview` 창이 앞에 있는지 확인합니다.
3. 왼쪽 위에서 다음 값을 확인합니다.
   - Target Actor: `BP_Taro_C_0`
   - Audio Source: `Local File`
   - 경로: `/home/aim/Downloads/video2.wav`
4. 초록색 ▶ 버튼을 **한 번만** 누릅니다.
5. 첫 요청은 NIM 준비와 결과 버퍼링 때문에 약 10~25초가 걸릴 수 있습니다. 이 시간 동안 버튼을 반복해서 누르지 않습니다.
6. 오디오가 시작되면 Taro의 입, 턱, 눈썹과 표정이 함께 움직이는지 확인합니다.

화면이 닫힌 경우 다음 명령으로 다시 실행합니다.

```bash
cd /home/aim/workspace/hosang/repo/facenet
DISPLAY=:1 XAUTHORITY=/home/aim/.Xauthority \
  A2F_DEMO_MODE=realtime \
  scripts/audio2face-metahuman/start-demo.sh
```

UE 프로세스에는 `CUDA_VISIBLE_DEVICES=1`을 주지 않습니다. RTX A4500 선택은 NIM 컨테이너의 device request로 이미 고정되어 있고, UE는 VNC surface presentation이 가능한 Quadro Vulkan adapter 0을 사용합니다.

## 5. 서비스 상태 확인

```bash
cd /home/aim/workspace/hosang/repo/facenet

docker ps --filter name=audio2face-3d-pretrained
curl -fsS http://127.0.0.1:8000/v1/health/ready
ss -ltn | grep -E ':52000|:8000|:6080'
```

정상 health 응답은 다음과 같습니다.

```json
{"object":"health.response","message":"ready","status":"ready"}
```

NIM 로그:

```bash
docker logs --tail 100 audio2face-3d-pretrained
```

UE 로그:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face-metahuman/KairosSample/Saved/Logs/TaroA2F/TaroA2FVNC.log
```

## 6. 최종 MP4 보기

최종 파일:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/final-taro-mrq/Taro_Audio2Face_video2_FINAL.mp4
```

VNC에서 재생:

```bash
DISPLAY=:1 XAUTHORITY=/home/aim/.Xauthority \
  totem /home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/final-taro-mrq/Taro_Audio2Face_video2_FINAL.mp4
```

최종 파일 사양:

| 항목 | 검증값 |
| --- | --- |
| Video | H.264 High, yuv420p, 1920×1080, 30 fps |
| Video duration | 10.000초, 300프레임 |
| Audio | AAC-LC, 44.1 kHz, stereo, 약 193 kbps |
| Audio duration | 10.008초 |
| Video start | 0.000초 |
| Audio start | 0.000초 |
| Stream start delta | 0 ms |
| Capture frame rounding | 영상 첫 프레임이 기록된 A2F audio-start보다 14.418 ms 빠름 |
| End duration delta | 오디오가 영상보다 8.005 ms 김 |
| Audio mean / max | -31.5 / -7.6 dBFS, 무음 아님 |
| SHA-256 | `9414a7479f2f5c25084683b7447f8ff695a48b6cdc339984b276046ae95a54b4` |

동기 수치는 Take Recorder 시작 시각, ACE audio-start 로그, 30 fps 프레임 경계를 이용한 타임라인 검증값입니다. 최종 파일은 noVNC의 Totem에서 실제 재생해 입 모양 변화와 오디오 재생도 함께 확인했습니다.

## 7. MP4를 다시 만드는 방법

MRQ PNG 프레임과 원본 WAV가 남아 있으므로 다음 한 줄로 최종 MP4를 재생성하고 자동 검증할 수 있습니다.

```bash
cd /home/aim/workspace/hosang/repo/facenet
scripts/audio2face-metahuman/finalize-taro-mp4.sh /home/aim/Downloads/video2.wav
```

이 스크립트는 시스템 FFmpeg를 사용하지 않습니다. 반드시 다음 프로젝트 로컬 wrapper만 사용합니다.

```text
/home/aim/workspace/hosang/repo/facenet/.tools/ffmpeg/bin/ffmpeg
/home/aim/workspace/hosang/repo/facenet/.tools/ffmpeg/bin/ffprobe
```

MRQ 결과:

```text
.tools/audio2face3d/final-taro-mrq/Taro_A2F_Taro.7055.png ... .7355.png
```

UE Movie Render Queue Command Line Encoder도 같은 로컬 FFmpeg로 실행했습니다. 다만 UE 5.6 encoder가 이번 렌더에서 301개 PNG 중 4프레임만 포함한 MP4를 만들었으므로, `Taro_A2F_Taro_video.mp4`는 실패 증거로만 보존합니다. 최종본은 검증된 전체 PNG 시퀀스와 원본 WAV를 로컬 FFmpeg로 결합한 `Taro_Audio2Face_video2_FINAL.mp4`입니다.

## 8. 검증 증거

| 증거 | 경로 |
| --- | --- |
| 공식 Taro 패키지 SHA | `.tools/audio2face3d/metahuman/Taro-k8bukITg-cinematic-complete.zip.sha256` |
| Taro 구성 로그 | `.tools/audio2face-metahuman/KairosSample/Saved/Logs/TaroA2F/configure-taro-face-body-pass2.log` |
| Vulkan 300-frame PASS | `.tools/audio2face-metahuman/KairosSample/Saved/Logs/TaroA2F/vulkan-taro-face-body-safe-top.log` |
| ACE/NIM 세션 로그 | `.tools/audio2face-metahuman/KairosSample/Saved/Logs/TaroA2F/TaroA2FVNC.log` |
| 발화 motion montage | `.tools/audio2face3d/final-taro-mrq/Taro_Audio2Face_video2_motion_montage.png` |
| VNC 최종 준비 화면 | `.tools/audio2face3d/gui-evidence/taro-final-vnc-ready-confirmed.png` |
| 실제 Totem 재생 화면 | `.tools/audio2face3d/gui-evidence/taro-final-mp4-totem-playback.png` |
| FFprobe JSON | `.tools/audio2face3d/final-taro-mrq/Taro_Audio2Face_video2_FINAL.ffprobe.json` |
| 볼륨 검사 | `.tools/audio2face3d/final-taro-mrq/Taro_Audio2Face_video2_FINAL.volume.txt` |

핵심 ACE 성공 로그는 다음과 같습니다.

```text
[ACE SID 2] Started RemoteA2F session at http://127.0.0.1:52000
[ACE SID 2 callback] received 301 animation samples, 882688 audio samples
```

## 9. 문제 해결

### 재생 버튼을 눌러도 바로 움직이지 않음

- 첫 요청에는 10~25초 정도 걸릴 수 있습니다.
- spinner 동안 다시 누르지 말고 NIM 로그에서 세션 진행을 확인합니다.
- `curl -fsS http://127.0.0.1:8000/v1/health/ready`가 실패하면 컨테이너를 시작합니다.

```bash
docker start audio2face-3d-pretrained
```

### `disconnected` 표시

- UE 설정의 RemoteA2F 주소는 `http://127.0.0.1:52000`입니다.
- 52000 포트와 NIM health를 확인합니다.
- UE와 NIM을 동시에 여러 번 재시작하지 않습니다.

### 화면이 검거나 Vulkan 오류가 남

- UE는 `-graphicsadapter=0`을 사용해야 VNC에 표시됩니다.
- RTX A4500은 NIM 추론 전용입니다.
- 드라이버 변경이나 재부팅은 이 데모에 필요하지 않으며 실행하지 않았습니다.

### noVNC에서 소리가 안 들림

원격 청취용 서비스는 다음 스크립트로 다시 시작할 수 있습니다.

```bash
scripts/audio2face-metahuman/start-novnc-audio-stream.sh
```

이 PulseAudio 스트림은 VNC 청취용일 뿐이며 최종 MP4의 오디오 소스가 아닙니다. 최종 MP4는 원본 `/home/aim/Downloads/video2.wav`를 authoritative audio track으로 사용합니다.

## 10. 안전하게 종료하기

UE만 종료하려면 noVNC에서 게임 창을 닫고 Unreal Editor를 종료합니다. NIM 컨테이너를 중지하려면 다음 명령을 사용합니다.

```bash
docker stop audio2face-3d-pretrained
```

다운로드, Take Recorder asset, MRQ 프레임, 로그, 최종 MP4는 삭제하지 말고 보존합니다.

## 11. 추가 산출물: `test.wav`

`/home/aim/Downloads/test.wav`로 별도 A2F 시연 영상을 만들고 검증했습니다.

최종 파일:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/final-taro-test-mrq/Taro_Audio2Face_test_FINAL.mp4
```

검증값:

| 항목 | 값 |
| --- | --- |
| 입력 | PCM s16le, 48 kHz, mono, 3.626667초 |
| A2F | SID 7, animation 109 samples, audio 174,080 samples |
| Video | H.264 High, yuv420p, 1920×1080, 30 fps, 109프레임, 3.633333초 |
| Audio | AAC-LC, 48 kHz mono, 약 142 kbps, 3.626초 |
| Stream start delta | 0 ms |
| End duration delta | 영상이 오디오보다 7.333 ms 김 |
| Audio mean / max | -29.1 / -12.8 dBFS, 무음 아님 |
| SHA-256 | `bb659492d8546e35f2c61f72867379912b96423a3132a798efba026e746e30a4` |

재생성 및 검증:

```bash
cd /home/aim/workspace/hosang/repo/facenet
scripts/audio2face-metahuman/finalize-taro-test-mp4.sh /home/aim/Downloads/test.wav
```

동작 비교 이미지는 다음 경로에 있습니다.

```text
.tools/audio2face3d/final-taro-test-mrq/Taro_A2F_test_motion_montage.png
```

### 11.1 초점 교정본(권장 최종본)

초기 렌더의 CineCamera는 피사체의 눈에서 `96.401 cm` 떨어져 있었지만 `Manual Focus Distance`가 Unreal 기본값인 `100000 cm`로 남아 있었습니다. 렌즈와 구도는 그대로 유지하고 초점 거리만 `96.4 cm`로 맞췄으며, 조리개는 얼굴 전체 심도를 확보하도록 `f/16`을 유지했습니다.

권장 최종 파일:

```text
/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/final-taro-test-mrq-focus-fixed/Taro_Audio2Face_test_FOCUS_FIXED_FINAL.mp4
```

| 항목 | 초점 교정 결과 |
| --- | --- |
| Camera focus | Manual, 96.4 cm, f/16 |
| Video | H.264 High, yuv420p, 1920×1080, 30 fps, 109프레임, 3.633333초 |
| Audio | 원본 `test.wav` 기반 AAC-LC, 48 kHz mono, 3.626초 |
| Stream start delta | 0 ms |
| End duration delta | 영상이 오디오보다 7.333 ms 김 |
| Audio mean / max | -29.1 / -12.8 dBFS, 무음 아님 |
| Face ROI sharpness | 기존 대비 frame 0 `28.17×`, frame 54 `27.83×`, frame 108 `35.95×` |
| SHA-256 | `d83a34a88a6fbf347e14ad9d60037492d78bf34e602d13aca48327167efade1d` |

재생성 및 검증:

```bash
cd /home/aim/workspace/hosang/repo/facenet
scripts/audio2face-metahuman/finalize-taro-test-focus-fixed-mp4.sh /home/aim/Downloads/test.wav
```

VNC에서 반복 재생할 때는 다음 프로젝트 GUI를 사용합니다. `Play/Pause`, `Restart`, `Loop`를 제공하며 짧은 영상이 끝나도 창이 유지됩니다.

```bash
DISPLAY=:1 XAUTHORITY=/home/aim/.Xauthority \
scripts/audio2face-metahuman/play-focus-fixed-demo.py
```

초점 교정 전 MP4와 PNG는 비교 증거로 보존하며 삭제하지 않습니다. VNC 실제 재생 증거는 다음 파일입니다.

```text
.tools/audio2face3d/gui-evidence/taro-test-focus-before-after.png
.tools/audio2face3d/gui-evidence/taro-test-focus-fixed-totem-paused-motion.png
.tools/audio2face3d/gui-evidence/taro-focus-fixed-demo-player.png
```

## 12. 임의 오디오 단일 CLI 자동화

NVIDIA 공식 NIM client, ACE 2.5 C++/Blueprint API, UE 5.6 `TakeRecorderSubsystem`, Epic MRQ Python host executor, 프로젝트 FFmpeg를 연결한 반복 실행용 CLI:

```bash
cd /home/aim/workspace/hosang/repo/facenet
scripts/audio2face-metahuman/run-a2f-metahuman.py /absolute/path/to/input.wav --name my-demo
```

새 4초 입력으로 120-frame H.264/AAC MP4를 생성하고 motion, 비무음 오디오, A/V 0 ms, full decode를 검증했다. 상세 구조, 공식 URL, 버전, exit code와 성공 run은 [audio2face-taro-cli-pipeline.ko.md](audio2face-taro-cli-pipeline.ko.md)에 있다.
