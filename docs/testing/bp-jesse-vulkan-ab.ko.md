# BP_Jesse Linux Vulkan A/B 진단 보고서

작성일: 2026-08-26
판정: **미완료 / driver A/B 대기**

## 완료 기준

유일한 완료 기준은 원본 `/Game/MetaHumans/Jesse/BP_Jesse`의 Face, Body, Torso, Legs, Feet, Hair와 groom 전체, 원래 skin/clothing materials 및 LOD를 유지한 상태에서 Audio2Face 발화를 확인하는 것입니다. `SimplifiedACEFaceActor`는 연결·animation seam 진단 증거일 뿐 최종 결과가 아닙니다.

## 자산 검증

- `Body/m_tal_nrw_body.uasset`: 존재, 4,933,028 bytes
- `BodyBaseColor.uasset`: 존재, 18,393,294 bytes
- MetaHuman VersionInfo: 4.1.2
- 원본 BP SCS: 14 nodes
- Skeletal: Face(8 LOD), Body(4), Torso(4), Legs(4), Feet(4)
- Groom: Hair, Eyebrows, Fuzz, Eyelashes, Mustache, Beard
- `LODSync`: `ForcedLOD=-1`, `MinLOD=0`

body 누락, 불완전 다운로드, 개별 clothing mesh 누락 가설은 기각됐습니다.

## 고정 실행 조건

- UE: 5.6.0-43139311
- OS: Ubuntu 24.04, kernel 7.0.0-28-generic
- NVIDIA: 580.173.02 Open Kernel Module, GSP 580.173.02
- Vulkan: Quadro adapter 0 또는 RTX A4500 adapter 1
- Harness: 640×360 RenderOffscreen, 30 FPS, 10 seconds/300 frames
- 원본 asset은 수정하지 않음
- 각 A/B는 복제 map의 component visibility 또는 instance material override만 변경

재현 명령:

```bash
bash scripts/audio2face-metahuman/test-jesse-vulkan-variant.sh AB04_FaceTorso
```

## A/B 결과

| Variant | 변경 변수 | 결과 |
| --- | --- | --- |
| `AB00_Face` | 원본 BP, Face only | PASS |
| `AB01_FaceBody` | Face + Body | PASS |
| `AB03_AllSkeletal` | Face + Body + Shirt + Slacks + Oxfords | `VK_FAIL` |
| `AB04_FaceTorso` | Face + Shirt | `VK_FAIL` |
| `AB05_FaceLegs` | Face + Slacks | `VK_FAIL` |
| `AB06_FaceFeet` | Face + Oxfords | `VK_FAIL` |
| `AB10`~`AB15` | Face + 각 원본 groom 1개 | 모두 PASS |
| `AB20_TorsoDefaultMaterial` | 동일 Cinematic Shirt mesh + DefaultMaterial | PASS |
| `AB21_LegsDefaultMaterial` | 동일 Cinematic Slacks mesh + DefaultMaterial | PASS |
| `AB22_FeetDefaultMaterial` | 동일 Cinematic Oxfords mesh + DefaultMaterial | PASS |
| `AB23_TorsoCinematicLOD1` | Cinematic Shirt의 LOD1 강제 | `VK_FAIL` |
| `AB26_TorsoRegularMesh` | non-Cinematic Shirt mesh + 원본 material | `VK_FAIL` |
| `AB30_BodyWithFabricMaterial` | PASS하던 Body mesh + Shirt fabric material | `VK_FAIL` |
| `AB31_TorsoWithBodyMaterial` | FAIL하던 Shirt mesh + Body skin material | PASS |
| `AB04` on A4500 | original Shirt/fabric, adapter 1 | `VK_FAIL` |
| `AB20` on A4500 | same Shirt mesh, DefaultMaterial, adapter 1 | PASS |

실패 signature는 모두 같습니다.

```text
VkResult=-13
VulkanPipeline.cpp:1666
VulkanUtil.cpp:999
```

## material parent와 공통 shader 기능

세 의상 instance는 서로 다른 중간 parent를 거치지만 모두 다음 base에 도달합니다.

```text
/Game/MetaHumans/Common/Materials/M_fabric_simpler
```

base 공통 속성:

- Opaque
- Default Lit
- Two Sided = true
- Use Material Attributes = true
- `bUsedWithClothing`

세 instance에서 공통으로 활성화된 static switch:

- `DoDetailVariation`
- `DoMacroVariation`
- `DoPaintedWear`
- `DoPillOnMobile`
- `B_DoMacroVariationOnMobile`

Fuzz, anisotropic, wrinkles, print, MaterialB switch는 세 의상 사이에서 값이 다른데도 모두 실패하므로 단독 공통 원인으로 볼 수 없습니다.

## 현재 결론

메시, 다운로드, body, groom, Cinematic LOD0 문제는 기각됐습니다. 최소 실패 조건은 `M_fabric_simpler` 계열 material을 draw하는 것입니다. 동일 material은 Body mesh에서도 실패하고, clothing mesh는 Body/Default material에서 통과합니다. Quadro(Turing)와 A4500(Ampere) 모두 580-open에서 같은 결과이므로 GPU 세대보다 **UE 5.6 Linux Vulkan + NVIDIA 580-open + fabric shader pipeline** 조합이 blocker입니다.

UE의 번들 `VK_LAYER_KHRONOS_validation`은 열거됐지만 Vulkan instance 생성에서 incompatible layer로 거부돼 추가 VUID는 얻지 못했습니다.

## 575.64.03 A/B 경계

Epic은 Linux Vulkan용 NVIDIA driver를 570 이상으로 명시하므로 575.64.03은 명목상 요구 범위 안입니다. NVIDIA는 575.64.03 x86_64 설치 파일과 checksum을 공식 배포합니다. NVIDIA 문서는 open/proprietary kernel module이 상호 배타적이며 user-space와 kernel-module source 버전을 일치시켜야 한다고 설명합니다.

- [Epic Linux requirements](https://dev.epicgames.com/documentation/unreal-engine/linux-development-requirements-for-unreal-engine)
- [NVIDIA 575.64.03 official index](https://download.nvidia.com/XFree86/Linux-x86_64/575.64.03/)
- [NVIDIA open kernel module rules](https://download.nvidia.com/XFree86/Linux-x86_64/575.64.03/README/kernel_open.html)

따라서 575 user-space library만 현재 580 kernel module과 섞는 실험은 안전하지 않습니다. A/B에는 시스템 driver 교체, X/VNC 중단, module rebuild, reboot가 필요하므로 사용자 승인 전에는 실행하지 않습니다.

## 승인 후 최소 A/B 순서

1. 현재 580.173.02 package/module/Xorg 상태와 rollback 경로 보존
2. 승인된 575.64.03 전체 driver stack 설치 후 reboot
3. `AB04_FaceTorso`와 `AB20_TorsoDefaultMaterial`만 먼저 재실행
4. `AB04`가 PASS로 바뀔 때만 `AB99_Full` 실행
5. Full render PASS일 때만 원본 BP에 ACE 연결을 추가한 복제 맵에서 Claire WAV 발화 검증
6. 하나라도 실패하면 완료 처리하지 않고 580으로 rollback

DefaultMaterial 및 face-only 결과는 어떤 경우에도 최종 해결로 인정하지 않습니다.
