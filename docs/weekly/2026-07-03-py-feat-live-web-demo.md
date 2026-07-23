# Py-Feat.Live Web Demo 주간 작업일지

## Py-Feat 개요

- 공식 사이트: [Py-Feat: Python Facial Expression Analysis Toolbox](https://py-feat.org/)
- 모델 설명: [Py-Feat Models](https://py-feat.org/pages/models/)
- 얼굴 표정 분석을 위한 Python 기반 오픈소스 툴박스
- 이미지/비디오에서 얼굴 검출, facial landmark, Action Unit, emotion, head pose, gaze 등을 분석
- AU(Action Unit): Facial Action Coding System 기반의 얼굴 근육 움직임 단위
- AU 분석 목적: 표정을 단일 감정 label이 아니라 눈썹, 눈꺼풀, 입술, 턱 등 얼굴 부위 움직임 조합으로 정량화
- Detectorv2 인식 항목: 20개 AU, 7-class emotion, valence/arousal, gaze, 478-point 3D face mesh, 6-DoF head pose, 52개 blendshape
- 성능 특성: Detectorv2는 단일 multi-task network가 여러 출력을 한 번에 예측하므로, 여러 모델을 순차 실행하는 Detectorv1보다 특히 single-frame 처리에서 빠른 구조
- 가속 지원: CUDA, Apple Silicon `mps`, batching 지원
- 이번 시연에서는 Detectorv2와 Apple Silicon `mps`를 활용해 웹캠 기반 실시간 분석 결과를 브라우저에서 렌더링

### Py-Feat 정량 성능

| 항목 | 공식 성능 지표 |
| --- | --- |
| AU detection | DISFA+ 12-AU macro-F1 `0.693`, DISFA+ 8-AU subset macro-F1 `0.740` |
| Emotion recognition | RAF-DB 7-class accuracy `0.910`, macro-F1 `0.885` |
| Emotion recognition | AffectNet 7-class accuracy `0.616`, macro-F1 `0.612` |
| Valence / Arousal | Aff-Wild2 validation CCC `0.852 / 0.799` |
| Gaze estimation | MPIIGaze mean angular error `7.05°`, Gaze360 mean angular error `12.89°` |
| MPS throughput | Apple M5 Max 기준 Detectorv2 short video batch 1 `32.5 FPS`, batch 16 `134.3 FPS` |
| MPS throughput | Apple M5 Max 기준 Detectorv2 long video batch 1 `30.1 FPS`, batch 16 `128.5 FPS` |

- 성능 출처: [face_multitask_v2 model card](https://huggingface.co/py-feat/face_multitask_v2), [Py-Feat M5 Max speed benchmark](https://github.com/cosanlab/py-feat/blob/main/docs/benchmarks/speed-clean-m5max.md)
- 현재 웹 시연 측정값: Brave Browser 캡처 기준 약 `22.1 FPS`, `45 ms latency`
- 해석: 공식 MPS benchmark는 모델 처리 throughput 기준이며, 웹 시연값은 카메라 캡처, JPEG 전송, API 처리, 브라우저 canvas 렌더링이 포함된 end-to-end 표시 성능

## Weekly Done

- Py-Feat Detectorv2 기반 Live 웹 시연 프로그램 구현
- 웹캠 입력 기반 얼굴 검출 및 facebox 실시간 렌더링
- 478-point face mesh overlay 구현
- Emotion, AU, pose, gaze, valence/arousal 분석 결과 표시
- 활성 AU 요약 및 전체 AU score 표시
- AU 설명을 Inspector 패널에 함께 제공
- 결과 영상과 분석 지표를 동시에 확인하는 Live 중심 2-column 레이아웃 적용
- Apple Silicon `mps` 환경에서 시연 가능 상태 확보
- 캡처 기준 약 `22.1 FPS`, `45 ms latency` 확인
- 실제 Brave Browser 실행 화면 캡처 정리

![Py-Feat.Live Web Demo 실행 화면](assets/py-feat-live-demo-render-2026-07-03.png)

## AU 설명

| AU | Description | 설명 |
| --- | --- | --- |
| AU01 | Inner Brow Raiser | 안쪽 눈썹 올림 |
| AU02 | Outer Brow Raiser | 바깥쪽 눈썹 올림 |
| AU04 | Brow Lowerer | 눈썹 내림 |
| AU05 | Upper Lid Raiser | 윗눈꺼풀 올림 |
| AU06 | Cheek Raiser | 볼 올림 |
| AU07 | Lid Tightener | 눈꺼풀 조임 |
| AU09 | Nose Wrinkler | 코 주름 |
| AU10 | Upper Lip Raiser | 윗입술 올림 |
| AU11 | Nasolabial Deepener | 코입술 고랑 깊어짐 |
| AU12 | Lip Corner Puller | 입꼬리 당김 |
| AU14 | Dimpler | 보조개 |
| AU15 | Lip Corner Depressor | 입꼬리 내림 |
| AU17 | Chin Raiser | 턱끝 올림 |
| AU20 | Lip Stretcher | 입술 당김 |
| AU23 | Lip Tightener | 입술 조임 |
| AU24 | Lip Pressor | 입술 누름 |
| AU25 | Lips Part | 입 벌림 |
| AU26 | Jaw Drop | 턱 내림 |
| AU28 | Lip Suck | 입술 빨아들임 |
| AU43 | Eyes Closed | 눈 감음 |

## Weekly TODO

- 실시간 추론 성능 안정화
- FPS 변동 폭 감소
- AU shade overlay 개선
- Inspector 패널 정보 밀도 개선
- 시연 중 핵심 결과가 더 잘 보이도록 UI 정리
- Viewer / Analyze / session 저장 기능 검증
- 최종 시연 흐름 기준 실행 방법 정리
- QA 체크리스트 작성
