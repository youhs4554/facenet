# Audio2Face-3D + MetaHuman CLI 핸즈온 작성 계약

## 한 문장 주장

처음 사용하는 사람도 canonical CLI로 입력 오디오를 얼굴 애니메이션과 선택적 자연스러운 머리 움직임이 포함된 MetaHuman 영상으로 변환할 수 있으며, 각 단계는 터미널·Unreal·산출물 증거와 지원 경계를 함께 확인할 수 있다.

## 독자와 문서의 역할

- **주 독자:** Linux 셸과 Unreal Editor를 처음 함께 사용하는 개발자·기술 아티스트
- **독자가 끝내야 할 작업:** `test.wav`로 head-motion OFF baseline을 만들고, 검증된 `resume` 경계로 head-motion ON MP4를 생성한 뒤 codec·A/V·얼굴·머리 동기를 확인한다.
- **문서가 하지 않는 일:** Epic 로그인·유료 자산 구매·MetaHuman 라이선스 우회·모델 학습·NVIDIA가 제공하지 않는 머리 움직임의 공식 기능화를 설명하지 않는다.

## 용어 ledger

| Canonical term | 처음 사용할 때의 정의 | 고정 표기 |
| --- | --- | --- |
| NVIDIA Audio2Face-3D v3.0 diffusion | 입력 음성을 얼굴 애니메이션 데이터로 변환하는 기본 모델 프로필 | `v3.0-diffusion` |
| NIM `multi_v3.2` | 설치된 v3 diffusion 추론 서비스의 모델 ID | `multi_v3.2`, endpoint `127.0.0.1:52100` |
| NVIDIA ACE 2.5 | Audio2Face 결과를 Unreal의 MetaHuman 얼굴 애니메이션 경로로 연결하는 설치 플러그인 | `ACE 2.5` |
| Unreal Engine 5.6 | Take Recorder, AnimSequence, Sequencer와 Movie Render Queue가 실행되는 렌더 환경 | `UE 5.6` |
| MetaHuman | `/Game/MetaHumans/.../BP_*`로 해결되는 Unreal 캐릭터 | `MetaHuman` |
| Movie Render Queue | Level Sequence를 최종 frame으로 렌더하는 Unreal 기능 | 처음 한 번 `Movie Render Queue (MRQ)`, 이후 `MRQ` |
| 로컬 run-owned baked Body/Face AnimSequence 머리 움직임 | 실행 전용 Body/Face 복사본의 `neck_01`, `neck_02`, `head`에 회전 키를 bake하는 로컬 확장 | `로컬 head motion`; implementation ID `local-run-owned-baked-body-animsequence` |
| final-render applied | 설정이 최종 MetaHuman MP4에 적용되고 capture/render 증거가 존재하는 상태 | `final-render applied` |
| inference-only | NIM 출력과 진단 artifact까지만 만들고 UE/MRQ를 생략하는 경계 | `inference-only` |
| resume | hash·model·endpoint가 일치하는 성공 inference 경계를 재사용하는 방식 | `--resume` |
| face-focused-vulkan-safe | source asset을 바꾸지 않고 run-owned 의상 표현만 안전한 opaque material로 대체하는 Linux Vulkan workaround | `face-focused-vulkan-safe` |
| A/V synchronization | 최종 MP4의 video/audio 시작 시각과 길이 정합 | `A/V 동기` |
| facial content synchronization | A2F `JawOpen`과 실제 렌더 얼굴 움직임의 frame-level 정합 | `얼굴 content 동기` |
| head-motion synchronization | 계획한 머리 pose와 렌더 optical motion의 frame-level 정합 | `머리 동기` |
| Claire reference geometry | MetaHuman retarget 전 A2F curve 변형을 보여 주는 진단 얼굴 | `Claire 기준 얼굴`; MetaHuman과 동일 얼굴로 표현 금지 |
| master clock | avatar·panel·audio가 함께 따르는 source audio seconds | `master clock` |

## Claim–evidence–boundary map

| 문서 주장 | 근거 | 경계 |
| --- | --- | --- |
| canonical 기본 모델은 v3 diffusion이다. | `a2f_model_registry.py`, r7 manifest의 `v3.0-diffusion`/`multi_v3.2`/52100 | v2는 삭제되지 않았고 명시적 legacy opt-in이다. 모델 비교 학습 절은 만들지 않는다. |
| r7은 실제 Taro head-motion ON 성공이다. | `20260829-110741-head-motion-sync-final-r7/manifest.json`, `head-motion-final-verification.json` | `/home/aim/Downloads/test.wav`, Taro, `close-up-front` 조건의 worked example이다. |
| 실제 목·머리 bone이 움직인다. | Body `neck_01/neck_02/head`, 0.2/0.3/0.5, nonzero authored delta, actual OFF/ON pixels | NVIDIA/ACE가 생성한 head output이 아니다. 해부학적 정확성 평가는 아니다. |
| 카메라 흔들림으로 만든 결과가 아니다. | OFF/ON camera transform equality, actor-root track absent | optical motion만으로 모든 skeletal detail을 증명하지 않는다. |
| 영상·음성·얼굴 동기가 통과했다. | H.264/AAC, A/V 0 ms, full decode, 얼굴 lag 0, correlation 0.8084 | 109 frame은 3.6267초 `test.wav`의 값이며 일반 상수가 아니다. |
| 계획한 머리 pose와 렌더가 정렬됐다. | optical best lag -1 frame(허용 ±1), zero-lag mean R² 0.9942 | 고정 ROI optical 검증이며 다른 avatar·camera의 동일 수치를 보장하지 않는다. |
| source MetaHuman은 수정하지 않았다. | `source_asset_modified=false`, run-owned baked Body/Face asset path | 실행 전용 asset과 render output은 새로 생성된다. |
| 로컬 네 avatar에서 실행됐다. | `20260829-head-motion-all-avatars/all-avatars-head-motion-verification.json` | 동일 입력에 대한 범위이며 성별·연령·민족 성능 일반화를 뜻하지 않는다. |
| Keiji source 실행은 안전하지 않다. | 반복된 `M_fabric_simpler` Vulkan PSO 실패와 safe-profile 성공 run | `VkResult=-13`은 `VK_ERROR_UNKNOWN`이며 GPU OOM으로 표현하지 않는다. |
| timecoded emotion은 최종 렌더 증거가 제한적이다. | current config/request 경로와 문서화된 evidence boundary | inference 변화만으로 MetaHuman emotion 성공을 주장하지 않는다. |

## 공식 제품/API 근거

- NVIDIA Audio2Face-3D support matrix: <https://docs.nvidia.com/ace/audio2face-3d-microservice/latest/text/support-matrix.html>
- NVIDIA ACE Unreal Plugin 2.5 Audio2Face: <https://docs.nvidia.com/ace/ace-unreal-plugin/2.5/ace-unreal-plugin-audio2face.html>
- NVIDIA ACE Unreal Plugin 2.5 character animation: <https://docs.nvidia.com/ace/ace-unreal-plugin/2.5/ace-unreal-plugin-animation.html>
- Epic UE 5.6 Take Recorder: <https://dev.epicgames.com/documentation/en-us/unreal-engine/take-recorder-in-unreal-engine?application_version=5.6>
- Epic UE 5.6 MRQ command-line rendering: <https://dev.epicgames.com/documentation/en-us/unreal-engine/using-command-line-rendering-with-move-render-queue-in-unreal-engine?application_version=5.6>
- Epic UE 5.6 `IAnimationDataController`: <https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/IAnimationDataController?application_version=5.6>

Context7 도구는 현재 harness에 노출되지 않았다. 공식 vendor URL과 설치된 UE/ACE source를 fallback primary evidence로 사용하며, local 성공 수치는 vendor 문서가 아니라 run manifest/verification으로 뒷받침한다.

## 스크린샷–stage map

| 번호 | Stage | 증거 유형 | 근거 run/표면 | 제시할 경계 |
| ---: | --- | --- | --- | --- |
| 01 | CLI help | 실제 terminal | canonical `--help` | 옵션 존재가 실행 성공을 증명하지 않는다. |
| 02 | 입력·NIM·GPU preflight | 실제 terminal | read-only `ffprobe`, `docker ps`, `nvidia-smi` | GPU memory만으로 UE render 성공을 증명하지 않는다. |
| 03 | baseline 실행 | 실제 terminal + deterministic replay | OFF run progress JSONL | historical replay이며 새 inference를 실행한 화면이 아니다. |
| 04 | head-motion 실행 | 실제 terminal + deterministic replay | r7 progress JSONL | `109`는 worked example이다. |
| 05 | head-motion manifest | 실제 terminal + deterministic projection | r7 final verification | bone authoring과 최종 pixel evidence를 함께 읽는다. |
| 06 | run-owned Unreal sequence | 실제 VNC GUI | UE 5.6 r7 FinalSequence frame 60 | Bridge/Fab은 per-process에서만 비활성화했다. Bone 수치 증거는 JSON과 함께 읽는다. |
| 07 | OFF/ON 결과 | 실제 MRQ pixels의 deterministic contact sheet | r7 OFF/ON | 생성 이미지가 아니다. |
| 08 | codec·동기 검증 | 실제 terminal | project-local ffprobe/ffmpeg + r7 manifest | stream start만으로 얼굴 동기를 통과시키지 않는다. |
| 09 | GUI 결과 확인 | 실제 VNC GUI | GNOME Image Viewer + r7 contact sheet | viewer는 결과 확인용이며 animation authoring 증거는 아니다. |

모든 source/crop/hash/dimension은 `screenshots/screenshot-manifest.json`에 기록한다. AI 생성·beautification은 사용하지 않는다.

## Reader action click-path audit

| Reader action | State transition | Artifact/evidence | Visible result | Recovery | Boundary |
| --- | --- | --- | --- | --- | --- |
| 입력/NIM/GPU 확인 | read-only preflight | ffprobe, container, GPU output | terminal PASS | path/service/collision 수정 | A2F·UE 성공 증거가 아님 |
| baseline 실행 | 새 run, head OFF | manifest, progress, MP4, verification | 고정 camera facial render | 실패 stage/log 확인 | head motion 증거 아님 |
| baseline manifest 선택 | verified inference/latency 경계 고정 | input/model/avatar/shot/fps hash | 다음 ON command의 `--resume` | mismatch면 새 baseline | 이전 render frame 재사용 아님 |
| head motion ON | deterministic samples와 run-owned bake | source/applied SHA, Body/Face assets | OFF/ON 실제 MetaHuman | exact calibration 또는 bounded retry | NVIDIA head output 아님 |
| avatar/safe profile 선택 | Asset Registry resolve, run-owned visual change | object path/profile/status | 선택 avatar bust render | official import/ACE readiness | safe profile은 animation 품질 개선 아님 |
| named/custom shot 선택 | resolved camera/LevelSequence | camera JSON, shot manifest | 구도별 render | schema/range 수정 | camera motion은 head motion이 아님 |
| ACE/Take Recorder/MRQ | run-owned capture와 frame render | capture/MRQ status, sequence/animation path | actual UE viewport와 MRQ pixels | collision/Vulkan evidence 보존 | frame만으로 audio·sync 증명 안 됨 |
| mux/verification | H.264/AAC와 content checks | ffprobe/decode/face/head sync JSON | final MP4/player | authoritative WAV remux 또는 calibrated retry | codec PASS만으로 자연스러움 증명 안 됨 |
