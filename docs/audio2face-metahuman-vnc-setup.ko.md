# Audio2Face → Unreal Engine MetaHuman VNC 데모 구축·사용 설명서

작성일: 2026-08-26
대상 서버: `aim-dev-server`
현재 상태: **이 문서의 Jesse 진단 기록은 보존되어 있으며, 최종 범위는 공식 아시아인 MetaHuman `Taro` 얼굴+Body+후드 상의 Audio2Face 데모와 H.264/AAC MP4 생성까지 완료되었습니다. 최신 실행 절차와 증거는 [Taro 최종 사용 설명서](audio2face-taro-demo-guide.ko.md)를 기준으로 합니다.**

> 아래 Jesse 재질/드라이버 A/B 내용은 원인 분리의 역사적 기록입니다. 현재 완료 기준에는 전체 Jesse 의상 렌더링이나 드라이버 변경이 포함되지 않습니다.

## 1. 결론

원본 NVIDIA On-Demand 세션 [Audio2Face to Metahuman Blendshape Streaming PART 1](https://www.nvidia.com/en-us/on-demand/session/omniverse2020-om1747/)은 2023년 Omniverse Audio2Face 앱이 두 개의 Live Link 스트림(얼굴 blendshape, 오디오)을 Unreal Engine으로 보내고 MetaHuman을 움직이는 구성입니다.

현재 NVIDIA는 구형 Omniverse Audio2Face facial-animation 파이프라인과 legacy Live Link interface를 deprecated/unsupported로 표시합니다. Linux 서버에서의 현행 공식 대체 경로는 다음과 같습니다.

```text
공식 Claire WAV
  → Linux Audio2Face-3D NIM 2.0 (Claire v2.3.1 pretrained, gRPC 52000)
  → UE 5.6 NVIDIA ACE 2.5 RemoteA2F provider
  → ACE Audio Curve Source Component
  → Epic MetaHuman Face animation
```

현재 서버에서 NIM 추론, UE 5.6/ACE 2.5 Linux 빌드, VNC Vulkan GUI를 검증했습니다. Jesse는 재질 문제의 진단 근거로 보존하고, 최종 데모는 Epic 공식 `Taro`의 원본 얼굴·눈·치아·모든 groom·Body와 원본 후드 메시를 사용합니다. Linux Vulkan에서 불안정한 원본 fabric parent 대신 복제 맵의 후드 컴포넌트에만 불투명 남색 재질을 덮어썼으며 원본 자산은 수정하지 않았습니다.

## 2. 원본 2023 Live Link 세션 구성

NVIDIA의 공식 legacy [Audio2Face to UE Live Link Plugin 문서](https://docs.omniverse.nvidia.com/audio2face/latest/user-manual/livelink-ue-plugin.html)에 따르면 구성 순서는 다음과 같습니다.

1. Audio2Face 2023.2 설치 폴더의 `ACEUnrealPlugin-5.3/ACE` 플러그인을 UE 프로젝트 `Plugins/` 아래로 복사합니다.
2. Unreal의 `Omniverse Audio2Face Live Link` 플러그인을 활성화합니다.
3. `Face_AnimBP`의 `mh_arkit_mapping_pose`를 플러그인이 제공하는 `mh_arkit_mapping_pose_A2F`로 바꿉니다.
4. MetaHuman Blueprint에 `Live Link Skeletal Animation Component`를 추가합니다.
5. `Window > Virtual Production > Live Link`에서 `NVIDIA Omniverse LiveLink` source를 추가합니다.
6. facial blendshape port, audio port, audio sample rate를 sender와 동일하게 설정합니다.
7. 오디오는 16 kHz입니다. Legacy 플러그인은 resampling을 하지 않으므로 입력 WAV와 수신 설정이 반드시 일치해야 합니다.
8. Live Link subject 기본값은 `Audio2Face`입니다.
9. `Face_AnimBP` 및 레벨의 MetaHuman actor에서 `LLink Face Subj = Audio2Face`, `LLink Face Head = true`로 설정합니다.
10. Runtime에서는 Live Link Source Preset을 저장하고 `BeginPlay` 시 `Apply to Client`를 호출합니다.

Legacy 문서는 animation/audio port를 설정 필드로 정의하지만 현재 접근 가능한 본문에 숫자 기본값을 제시하지 않습니다. 구형 플러그인 바이너도 이 Linux 호스트에 없으므로 숫자를 추측하지 않았습니다.

## 3. 현행 공식 대체 경로와 원본과의 차이

| 항목 | 2023 원본 | 2026 현행 Linux 경로 |
| --- | --- | --- |
| 추론 runtime | Omniverse Audio2Face 앱 | Audio2Face-3D NIM 2.0 |
| UE 연결 | `NVIDIA Omniverse LiveLink` source | ACE 2.5 `RemoteA2F` provider |
| 전송 | animation/audio Live Link socket | Audio2Face-3D gRPC |
| 서버 port | 플러그인 UI에서 sender와 일치 | `127.0.0.1:52000` (실제 검증) |
| 오디오 | sender와 UE가 같은 16 kHz | ACE가 runtime에 16 kHz mono로 변환 |
| MetaHuman 컴포넌트 | Live Link Skeletal Animation Component | ACE Audio Curve Source Component |
| 얼굴 mapping | `mh_arkit_mapping_pose_A2F`, `Audio2Face` subject | NVIDIA 공식 sample의 MetaHuman curve mapping |
| Linux | 구형 A2F/Live Link 파이프라인 미지원 | ACE `RemoteA2F` 지원 |
| 로컬 UE inference | 해당 없음 | Windows만 지원; Linux는 NIM/NVCF remote 사용 |

NVIDIA의 현행 [Audio2Face-3D 허브](https://github.com/NVIDIA/Audio2Face-3D)는 ACE UE 2.5를 UE 5.5/5.6용으로 제공하며, 공식 sample 프로젝트가 MetaHuman mapping을 포함한다고 명시합니다. 단, Epic 규정 때문에 sample 다운로드에 MetaHuman 캐릭터 자체는 포함되지 않습니다.

## 4. 현재 서버 점검 결과

### 4.1 하드웨어와 운영체제

| 항목 | 결과 |
| --- | --- |
| OS | Ubuntu 24.04.4 LTS |
| GPU 0 | Quadro RTX 5000, 16 GB, compute 7.5 |
| GPU 1 | NVIDIA RTX A4500, 20 GB, compute 8.6 |
| Driver | `580.173.02` |
| 시스템 디스크 | 476 GB 여유 |
| `/mnt/t7` | 148 GB 여유 |
| RAM | 62 GB, 가용 약 53 GB |

### 4.2 VNC

| 항목 | 결과 |
| --- | --- |
| DISPLAY | `:1` |
| XAUTHORITY | `/home/aim/.Xauthority` |
| Desktop | XFCE / TigerVNC |
| 해상도 | 1920×1080, 24-bit |
| DBus | VNC 로그인마다 바뀌므로 실행 스크립트가 XFCE 프로세스에서 자동 탐지 |
| OpenGL | Mesa llvmpipe 4.5 |
| UE renderer | Vulkan, Quadro RTX 5000, driver 580.173.02 |
| A2F inference | RTX A4500 전용 (`device=1`) |
| VirtualGL | 설치됨; 현재 UE Vulkan 직접 실행에는 불필요 |

VNC의 일반 OpenGL은 CPU llvmpipe이지만 UE를 `-vulkan -graphicsadapter=0`으로 실행하면 NVIDIA Quadro RTX 5000을 사용하고 VNC `:1`에 swapchain을 정상 생성합니다. A4500을 `-graphicsadapter=1`로 직접 지정하면 장치는 선택되지만 현재 X11 화면에 연결되지 않아 `Cannot find a compatible Vulkan device that supports surface presentation`으로 종료됩니다. 따라서 최고 성능·안정성 구성은 **A4500=NIM inference, Quadro=VNC 렌더링**의 GPU 분리입니다.

### 4.3 설치 유무

- Unreal Engine: `UE 5.6.0-43139311`, 설치 완료
- Fab: `0.0.5`, UE 5.6 플러그인 설치 완료
- Quixel Bridge: `2025.0.1`, UE 5.6 플러그인 설치 및 GUI 로드 완료
- NVIDIA ACE: `2.5.0-20250614-2282`, Linux RemoteA2F 모듈 설치 완료
- Kairos Sample: Linux `Development Editor` 빌드 성공
- Epic MetaHuman Jesse: Cinematic 전체 자산 import 완료; 원본 `BP_Jesse` Vulkan 실행은 미완료
- Omniverse Launcher/legacy Audio2Face 앱: 설치하지 않음(현행 Linux 공식 경로가 아님)
- Audio2Face-3D pretrained NIM: 실행 중

## 5. 현재 실행 중인 pretrained Audio2Face-3D

| 항목 | 값 |
| --- | --- |
| Container | `audio2face-3d-pretrained` |
| Image | `nvcr.io/nim/nvidia/audio2face-3d:2.0` |
| Image digest | `sha256:6112996e0cbfd7a09d8555712bf3d03142da7bed6cade8cddcf0a6308312df71` |
| NIM 보고 버전 | `2.0.0-rc8`, API `3.1.0` |
| Model | Claire v2.3.1 regression |
| GPU | RTX A4500만 노출 (`device=1`) |
| gRPC | `127.0.0.1:52000` |
| HTTP health | `127.0.0.1:8000` |
| Restart policy | `unless-stopped` |
| TensorRT cache | `.tools/audio2face3d/nim-cache/` (1.3 GB) |

건강 확인:

```bash
docker ps --filter name=audio2face-3d-pretrained
curl -fsS http://127.0.0.1:8000/v1/health/ready
```

NIM 시작/중지/로그:

```bash
docker start audio2face-3d-pretrained
docker stop audio2face-3d-pretrained
docker logs -f --tail 200 audio2face-3d-pretrained
```

## 6. 검증된 Claire 추론 증거

공식 NVIDIA Samples 저장소의 5초 WAV를 사용했습니다.

```text
.tools/audio2face3d/Audio2Face-3D-Samples/example_audio/
└── Claire_sadness_16khz_5_sec.wav
```

실행 명령:

```bash
cd /home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/Audio2Face-3D-Samples/scripts/audio2face_3d_microservices_interaction_app
./.venv/bin/python a2f_3d.py health_check --url 127.0.0.1:52000
./.venv/bin/python a2f_3d.py run_inference \
  ../../example_audio/Claire_sadness_16khz_5_sec.wav \
  config/config_claire.yml \
  -u 127.0.0.1:52000 --print-fps
```

검증 결과:

- gRPC health: `ONLINE`
- NIM inference status: `SUCCESS`
- 관찰 FPS: 77.99
- animation: 157 frames, 68 blendshapes, 0.0~5.2 s
- emotion: 157 frames, 10 emotions
- 반환 audio: PCM-16, mono, 16 kHz, 5.233 s
- blendshape/emotion: 모두 유한값, timecode 단조 증가

결과 폴더:

```text
.tools/audio2face3d/Audio2Face-3D-Samples/scripts/
└── audio2face_3d_microservices_interaction_app/output_000001/
    ├── animation_frames.csv
    ├── a2f_3d_input_emotions.csv
    ├── a2f_3d_smoothed_emotion_output.csv
    └── out.wav
```

## 7. 다운로드·설치된 공식 파일

원본 다운로드 파일은 삭제하지 않고 `/home/aim/Downloads/`에 보존했습니다.

| 파일 | 크기 | SHA-256 | 검증 |
| --- | ---: | --- | --- |
| `Linux_Unreal_Engine_5.6.0.zip` | 30,839,841,519 B | `bb8f9efe2f0bdbf5dedce2d451ed96bb1d529b9ed5ba08358b68f0507041624a` | `unzip -t` PASS |
| `Linux_Fab_5.6.0_0.0.5.zip` | 26,948,689 B | `4bc6b0b535c567bdcf3567a78292e67def91058d0318ea6755fb4f0de7bea72f` | `unzip -t` PASS |
| `Linux_Bridge_5.6.0_2025.0.1.zip` | 37,822,222 B | `8beb1f983d32a662f074a6162a6299cf7b102013a0576a1f22fb61a7cbe1c972` | `unzip -t` PASS |
| `NV_ACE_Reference-UE5.6-v2.5.0rc3 (1).zip` | 3,418,110,172 B | `28b205418be6229c751df1fa57259eca59c0dc8d6039404007cfaca11d3f29d2` | `unzip -t` PASS |
| `KairosSample-UE5-Source-CL233291.7z` | 592,316,476 B | `fe8fec3a49ff1f6d77db44c9b6f3ae8fc26c5236270ad9ceb50d6cfa8d9b050c` | `7z t` PASS |

UE 5.8.2 압축 파일도 보존했지만 ACE 2.5의 공식 지원 범위가 UE 5.5/5.6이므로 설치·사용하지 않았습니다.

설치 경로:

```text
.tools/audio2face-metahuman/
├── UE_5.6/                         # 5.6.0-43139311
├── ACEPlugin/NV_ACE_Reference/    # 2.5.0-20250614-2282
└── KairosSample/                  # NVIDIA 공식 sample
```

ACE와 UE의 `UnrealEditor.modules` Build ID는 모두 `43139311`로 일치합니다. Kairos의 `EngineAssociation`을 5.6으로 갱신하고, 프로젝트 플러그인 경로 `KairosSample/Plugins/NV_ACE_Reference`를 공식 ACE 설치로 연결했습니다.

Linux editor 빌드 명령과 결과:

```bash
.tools/audio2face-metahuman/UE_5.6/Engine/Build/BatchFiles/Linux/Build.sh \
  KairosSampleEditor Linux Development \
  -Project="$PWD/.tools/audio2face-metahuman/KairosSample/KairosSample.uproject" \
  -WaitMutex -NoHotReload
```

- 결과: PASS
- 작업: 52 actions
- 소요: 45.47 s
- 산출물: `KairosSample/Binaries/Linux/libUnrealEditor-KairosSample.so`

## 8. UE/ACE 설정과 실행

프로젝트 `Config/DefaultEngine.ini`의 실제 설정:

```ini
[/Script/ACECore.ACESettings]
ACEConnectionInfo=(DestURL="http://127.0.0.1:52000",APIKey="",NvCFFunctionId="",NvCFFunctionVersion="")
BurstMode=ForceBurstMode
```

URL에는 NVIDIA 문서 요구대로 `http://` scheme을 포함했습니다. API key나 토큰은 로컬 NIM 연결에 필요하지 않으며 파일·로그에 기록하지 않았습니다.

일상 실행은 저장소 루트에서 다음 한 줄을 사용합니다.

```bash
./scripts/audio2face-metahuman/start-demo.sh
```

스크립트는 다음을 자동 수행합니다.

1. 기존 UE 중복 실행 여부를 확인합니다.
2. NIM이 중지되어 있으면 `audio2face-3d-pretrained` 컨테이너를 시작하고 health를 최대 120초 기다립니다.
3. VNC XFCE 프로세스에서 현재 `DBUS_SESSION_BUS_ADDRESS`와 `XDG_RUNTIME_DIR`를 읽습니다.
4. `DISPLAY=:1`, `/home/aim/.Xauthority`, Vulkan으로 Kairos를 실행합니다.
5. NIM/CUDA는 `CUDA_VISIBLE_DEVICES=1`(RTX A4500), UE Vulkan은 `-graphicsadapter=0`(VNC에 연결된 Quadro)으로 분리합니다.
6. `SDL_AUDIODRIVER=pulseaudio`와 VNC의 `XDG_RUNTIME_DIR`를 전달해 PipeWire/PulseAudio `auto_null` 장치를 준비합니다. 이 장치는 ACE animation curve와 오디오 재생 시계를 동기화하는 데 필요합니다.
7. VNC CEF/Bridge의 Vulkan 충돌을 피하려고 CEF만 CPU compositing으로 실행합니다.
8. `low-latency` 모드에서 ACE가 RemoteA2F 연결을 미리 할당하고 짧은 WAV를 Burst로 전송합니다.

기본값은 10초 이하의 시연 클립용 `low-latency`입니다. NVIDIA ACE 2.5는 RemoteA2F에서 10초를 넘는 클립에 Burst mode를 권장하지 않으므로, 긴 클립은 다음처럼 실시간 전송 모드로 실행합니다.

```bash
A2F_DEMO_MODE=realtime ./scripts/audio2face-metahuman/start-demo.sh
```

로그:

```text
.tools/audio2face-metahuman/KairosSample/Saved/Logs/KairosVNC.log
.tools/audio2face-metahuman/KairosSample/Saved/Logs/KairosVNC-console.log
```

실제 GUI 검증:

- `KairosSample - Unreal Editor` 창이 VNC `:1`에 1920×1080으로 표시됨
- UE가 Quadro RTX 5000 Vulkan adapter 0에서 렌더링
- NIM이 RTX A4500에서 약 2.7 GiB VRAM 사용
- Vulkan present/swapchain 생성 성공
- ACE Linux RemoteA2F 모듈과 NVIDIA AIM gRPC plugin 로드 성공
- Quixel Bridge 2025.0.1 로드 후 14,721 assets/66 MetaHumans 표시
- 진단용 face-only actor에서 Jesse face mesh의 원본 15개 얼굴 material slot이 개별·동시 렌더링됨을 확인
- ACE RemoteA2F session에서 157 animation samples/83,733 audio samples 수신 및 재생 확인
- async 요청 시작 frame `[782]`에서 재생 시작 frame `[988]`까지 UE frame이 계속 증가해 UI freeze 제거 확인

GUI 증거:

```text
.tools/audio2face3d/gui-evidence/kairos-editor-vnc.png
.tools/audio2face3d/gui-evidence/kairos-bridge-restarted.png
.tools/audio2face3d/gui-evidence/kairos-bridge-search-jesse-result.png
.tools/audio2face3d/gui-evidence/kairos-bridge-signin.png
.tools/audio2face3d/gui-evidence/kairos-final-camera-120.png
.tools/audio2face3d/gui-evidence/final-jesse-motion/frame-1.png
.tools/audio2face3d/gui-evidence/final-jesse-motion/frame-8.png
```

## 9. VNC에서 사용자가 지금 해야 할 최소 단계

UE와 NIM은 진단용 fallback 상태로 실행할 수 있습니다. 아래 절차는 A2F 기능 확인용이며 전체 Jesse 완료 증거로 사용하지 않습니다.

1. `KairosSample - Unreal Editor` 창을 엽니다.
2. 화면 왼쪽의 상태 점에 마우스를 올려 `Connected`인지 확인합니다.
3. `Audio Source`가 `Local File`인지 확인합니다.
4. WAV 경로가 아래 Claire 파일인지 확인합니다.
5. 녹색 Run 버튼을 **한 번만** 누릅니다.
6. 검증된 5초 Claire WAV는 약 0.2초 안에 오디오와 얼굴 애니메이션을 시작합니다.
7. 재생 중 Jesse의 입·턱·눈썹 표정이 오디오와 함께 움직이는지 확인합니다.

다른 WAV를 시험하려면 folder 버튼으로 PCM WAV를 선택하고 Run을 한 번 누르면 됩니다. 권장 입력은 mono, PCM-16, 16 kHz입니다.

## 10. 처음부터 다시 실행하는 step-by-step 절차

1. 저장소 루트로 이동합니다.

   ```bash
   cd /home/aim/workspace/hosang/repo/facenet
   ```

2. NIM과 UE를 실행합니다.

   ```bash
   ./scripts/audio2face-metahuman/start-demo.sh
   ```

3. health가 ready인지 확인합니다.

   ```bash
   curl -fsS http://127.0.0.1:8000/v1/health/ready
   ```

4. VNC `:1`에서 Unreal Editor가 열린 뒤 상단 Play를 누릅니다.
5. Target Actor의 `SimplifiedACEFaceActor`는 진단용 fallback입니다. 전체 완료 검증에서는 반드시 원본 `/Game/MetaHumans/Jesse/BP_Jesse`를 선택해야 합니다.
6. `Audio Source > Local File`을 선택합니다.
7. 다음 파일을 지정합니다.

   ```text
   /home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/Audio2Face-3D-Samples/example_audio/Claire_sadness_16khz_5_sec.wav
   ```

8. `Audio2Face > Settings`에서 `Server URL`과 `http://127.0.0.1:52000`을 선택하고 Enter/Tab으로 저장합니다. 이후 상태 툴팁이 `Connected`여야 합니다.
9. 녹색 Run을 한 번 누릅니다. 처리 중에도 UI가 멈추지 않아야 합니다.
10. Jesse의 입·턱·표정 움직임을 확인합니다.
11. 로그에서 다음 세 줄을 확인합니다.

    ```text
    Started RemoteA2F session at http://127.0.0.1:52000
    start playing audio on SimplifiedACEFaceActor
    received 157 animation samples, 83733 audio samples
    ```

12. 종료할 때는 PIE의 빨간 Stop을 누른 뒤 Unreal Editor를 닫습니다. NIM을 끄려면 별도로 `docker stop audio2face-3d-pretrained`를 실행합니다.

현행 ACE RemoteA2F는 입력 sample rate를 처리할 수 있지만, 원본 시연과 검증된 NIM sample을 맞추기 위해 PCM-16 mono 16 kHz Claire WAV를 사용합니다.

## 11. 현재 blocker와 다음 안전 실험

- 현재 VNC는 Quadro에 연결되어 있으므로 A4500은 UE 화면을 직접 present할 수 없습니다. A4500은 NIM inference 전용으로 사용합니다.
- Linux Vulkan에서 원본 `BP_Jesse`의 body/clothing/hair 전체 조합은 `VulkanPipeline.cpp:1666`, `VkResult=-13` graphics pipeline 생성 오류를 반복 재현했습니다. face-only actor는 원인 분리용이며 원본 BP를 대체하지 않습니다.
- 현재 드라이버는 `580.173.02` open kernel module입니다. 드라이버 회귀 가능성을 배제하지 않았고 `575.64.03` A/B가 필요할 수 있지만, 시스템 드라이버 변경은 사용자 승인 전에는 실행하지 않습니다.
- 다음 안전 실험은 드라이버를 건드리지 않고 NullRHI에서 원본 BP 컴포넌트별 visibility variant를 저장한 뒤, Vulkan에서 body/clothing/groom을 한 그룹씩 추가해 최초 실패 컴포넌트를 식별하는 것입니다.
- 위 실험 결과 세 clothing mesh 자체는 정상이며 공통 `/Game/MetaHumans/Common/Materials/M_fabric_simpler` shader pipeline이 최소 blocker로 확인됐습니다. 상세 재현표와 로그 경로는 [`docs/testing/bp-jesse-vulkan-ab.ko.md`](testing/bp-jesse-vulkan-ab.ko.md)에 기록했습니다.
- NVIDIA 공식 Kairos 5.6 UI는 deprecated 동기 함수를 호출합니다. 프로젝트 로컬 ACE 소스에서 이 호출만 NVIDIA의 공식 `UAsyncActionAnimateCharacter`로 전달해 UI freeze를 제거했습니다.
- 최신 [ACE 2.5 Audio2Face-3D 문서](https://docs.nvidia.com/ace/ace-unreal-plugin/latest/ace-unreal-plugin-audio2face.html)에 따라 짧은 데모에는 `Force Burst Mode`를 적용하고, `Allocate Audio2Face-3D Resources`로 RemoteA2F 연결을 미리 생성합니다. 기본 0.1초 재생 버퍼는 문서 권장값을 유지합니다.
- 배포된 ACE 2.5 `FA2FRemote`는 문서에 설명된 원격 자원 사전 할당 함수를 재정의하지 않아 기본 구현이 no-op이었습니다. 프로젝트 로컬 플러그인에 `AllocateResources() → IsConnectionAvailable()` 호환성 패치를 추가했고, 로그에서 첫 요청 1.44초 전에 연결 완료를 확인했습니다.
- 최신 [ACE 2.5 지원 행렬](https://docs.nvidia.com/ace/ace-unreal-plugin/latest/ace-unreal-plugin-support-matrix.html)은 Linux 로컬 모델 실행을 지원하지 않으므로, Windows 전용 모델 플러그인으로 우회하지 않고 현재 Linux RemoteA2F+NIM 구성을 유지합니다.
- 구형 2023 Live Link source/subject UI 대신 현행 공식 RemoteA2F gRPC 경로를 사용합니다.

## 12. 보존된 이전 작업

- Claire licensed dataset: 1.3 GB, Git LFS 검증 성공
- preprocessing run: `260826_012234_example`, 386 MB
- 중단된 training run: `260826_012350_example-diffusion`
- 학습 중단 시점: 약 epoch 44/400
- 보존 내용: 로그, TensorBoard event, config/state 파일 240 KB
- 완성 checkpoint: 중단 시점에 아직 생성되지 않음

새 학습/파인튜닝은 실행하지 않았으며, 위 산출물을 삭제하지 않았습니다.

## 13. 완료 판정 체크리스트

- [x] 새 학습 없음
- [x] 원본 legacy Live Link 구성 확인
- [x] 현행 Linux RemoteA2F 경로 선정
- [x] pretrained Claire NIM 추론 검증
- [x] NVIDIA ACE UE plugin/sample 다운로드 및 압축 무결성 검증
- [x] UE 5.6.0, Fab, Bridge 설치
- [x] ACE plugin 활성화, Linux editor 빌드, RemoteA2F URL 설정
- [x] VNC `:1`에서 UE Vulkan GUI와 Quixel Bridge/Jesse 화면 확인
- [x] Jesse MetaHuman 전체 자산 import 및 진단용 face material 15개 A/B
- [x] `ACE Audio Curve Source`와 NVIDIA ACE-modified `Face_AnimBP` 구성
- [x] 구형 동기 호출을 공식 async action으로 전달해 Run 시 UI freeze 제거
- [x] 진단용 `SimplifiedACEFaceActor`에서 Claire WAV facial animation 시각 검증
- [x] RTX A4500 NIM + Quadro VNC render의 듀얼 GPU 분리 검증
- [x] 최신 ACE 2.5 Burst mode와 RemoteA2F 자원 사전 할당 적용
- [x] 동일 조건 3회 반복에서 첫 애니메이션 p50 200 ms/p95 202 ms와 29.9~30.0 FPS 검증
- [ ] 원본 `/Game/MetaHumans/Jesse/BP_Jesse`의 hair/groom, eyes, teeth, head, neck, body, skin/clothing materials와 LOD 전체 렌더링
- [ ] 전체 원본 `BP_Jesse`에서 Claire WAV Audio2Face 발화 시각 검증

## 14. 저지연 벤치마크

측정 조건은 UE 5.6.0, ACE 2.5, Quadro RTX 5000 Vulkan 렌더링, RTX A4500 NIM 추론, RemoteA2F `127.0.0.1:52000`, 0.1초 재생 버퍼, 5초 Claire PCM-16 mono 16 kHz WAV로 고정했습니다. 각 모드를 세 번 교차 실행했습니다.

| 지표 | 기존 Real-Time | 저지연 Burst+사전 할당 | 변화 |
| --- | ---: | ---: | ---: |
| 버튼→첫 애니메이션 p50 | 4,599 ms | 200 ms | 95.6% 단축 |
| 버튼→첫 애니메이션 p95 | 4,617 ms | 202 ms | 95.6% 단축 |
| 오디오 전송 완료 p50 | 6,299 ms | 1,870 ms | 70.3% 단축 |
| 재생 중 렌더 cadence | 29.1~30.0 FPS | 29.9~30.0 FPS | 회귀 없음 |

모든 실행은 동일하게 animation 157 samples와 audio 83,733 samples를 수신했고 정상 종료했습니다. 재현 명령은 다음과 같습니다.

```bash
./scripts/audio2face-metahuman/benchmark-low-latency.sh baseline 1
./scripts/audio2face-metahuman/benchmark-low-latency.sh optimized 1
```

개별 JSON과 로그는 `.ecc/benchmarks/audio2face/`에 저장합니다.
