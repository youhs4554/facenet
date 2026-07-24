# MindPlus-Face Face Landmark 분석 주간 자료

## Weekly Done

> 과제 1차년도 요구사항인 Face Landmark 분석을 위한 오픈소스(Py-Feat) 조사 및 프로토타입 개발

> AFLFP·DISFA 공개 데이터셋을 이용한 Landmark·Action Unit 정량 성능 검증

> 연구노트 작성 및 6월분 전체 정리

## Py-Feat 개요

- [Py-Feat 공식 사이트](https://py-feat.org/) · [Py-Feat Models](https://py-feat.org/pages/models/)
- 얼굴 검출, Facial Landmark, Action Unit(AU), 감정, 머리 자세, 시선 등을 분석하는 Python 기반 오픈소스 도구
- AU는 표정을 단일 감정으로 분류하지 않고 입술·턱·눈썹 등 얼굴 근육의 움직임 단위로 정량화하는 지표
- `Detectorv2`는 여러 얼굴 지표를 한 번에 예측하며 Apple Silicon `mps`와 배치 처리를 지원
- 본 과제에서는 전체 출력 중 비식별 Landmark와 구강·하악 관련 AU를 Face Transformer의 입력 후보로 검토

## 공개 데이터셋 기반 성능 검증

| 데이터셋 | 데이터셋의 과제 | 본 과제와의 연관성 | 평가 표본 |
| --- | --- | --- | ---: |
| [AFLFP](https://ieeexplore.ieee.org/document/9177259) | 안면마비 얼굴의 16개 움직임에서 68개 Landmark 위치 검출 | 표정과 좌우 비대칭이 있는 상황에서 얼굴 형태를 안정적으로 추적할 수 있는지 확인 | 1,136장 |
| DISFA | 자연스러운 표정 영상에서 12개 AU의 발생 여부와 강도 분석 | 구강·하악 관련 AU12·25·26을 구분할 수 있는지 확인 | 5,400프레임 |

### 평가 방법

- 별도 학습 없이 사전학습된 Py-Feat `Detectorv2`를 그대로 사용
- 고정된 표본과 평가 기준을 적용하여 동일한 결과를 재현할 수 있도록 구성
- Landmark는 위치 오차(NME), AU는 검출 성능(F1), 처리 속도는 모델 추론 FPS로 평가

### NME 계산 방법

$$
\mathrm{NME}
=
\frac{1}{L}
\sum_{i=1}^{L}
\frac{\left\lVert \hat{\mathbf{p}}_i-\mathbf{p}_i \right\rVert_2}
{\sqrt{w h}}
$$

- $L$: Landmark 수(68개)
- $\hat{\mathbf{p}}_i$, $\mathbf{p}_i$: $i$번째 Landmark의 예측 위치와 실제 위치
- $w$, $h$: 실제 얼굴 영역의 너비와 높이
- 얼굴 크기가 다른 표본을 비교할 수 있도록 평균 위치 오차를 얼굴 영역 크기로 나눈 값이며, 낮을수록 정확
- 이번 결과인 NME `6.37%`는 Landmark의 평균 위치 오차가 얼굴 영역 크기($\sqrt{wh}$)의 약 `6.37%`임을 의미

## 주요 결과

| 평가 항목 | 결과 | 해석 |
| --- | ---: | --- |
| AFLFP Landmark 검출 | `100%` | 전체 표본에서 Landmark 산출 |
| AFLFP 평균 Landmark 오차 | `6.37%` | 16개 얼굴 움직임에서 비교적 일정한 추적 결과 확인 |
| DISFA AU 분석 | `100%` | 전체 평가 프레임에서 AU 결과 산출 |
| DISFA 12개 AU 평균 성능 | macro F1 `0.714` | AU를 보조 지표로 활용할 가능성 확인 |
| 모델 추론 속도 | 약 `25~26 FPS` | 배치 기반 특징 추출이 가능한 수준 |

### 주요 시각화

![AFLFP 움직임별 Landmark 오차](assets/2026-07-24/aflfp_nme.png)

그림 1. AFLFP의 움직임별 Landmark 오차 분포. 움직임별 평균 오차가 약 6%대에서 비교적 일정하게 나타났다. 아래의 기존 논문 수치는 평가 조건이 달라 참고값으로만 사용했다.

![DISFA AU별 F1 및 ICC](assets/2026-07-24/disfa_au_metrics.png)

그림 2. DISFA의 AU별 검출 성능(F1)과 강도 일치도(ICC). 구강·하악 관련 AU12·25·26에서 모두 분석 결과를 산출했다.

## 핵심 AU 결과

| AU | 설명 | 프로젝트에서의 의미 | F1 |
| --- | --- | --- | ---: |
| AU12 | 입꼬리 당김 | 하부 안면 움직임 및 표정 저하 확인 | `0.737` |
| AU25 | 입술 벌어짐 | 구강 개폐 패턴 확인 | `0.959` |
| AU26 | 턱 내림 | 턱 하강 및 구강 개구량 확인 | `0.785` |

- AU25가 가장 높은 성능을 보였으며 AU12·26도 구강운동 보조 지표로 검토 가능한 수준의 결과를 확인
- 이번 결과는 공개 데이터 기반의 기술 검증으로, 질환 감별 성능이나 임상적 유효성을 검증한 결과는 아님
- 실제 Task 2(AMR/SMR)와 Task 5(문단읽기) 영상 및 IRB 기반 임상 데이터에서 추가 검증 필요

## 1차년도 과업과의 연계

- Py-Feat의 Landmark·AU 추출 기능과 한계를 공개 데이터로 확인하여 오픈소스 후보 검토를 1차 완료
- Face Transformer 입력 후보와 Landmark 오차·AU별 F1 등 프로토타입 평가 기준을 구체화
- 이번 평가는 공개 데이터만 사용했으므로 경북대학교병원의 IRB 기반 100세션 수집 실적에는 포함되지 않음

## Weekly TODO

| 범주 | 구현·검증할 세부 지표 | 관련 과제 |
| --- | --- | --- |
| 구강운동 | 구강 개구량, 입술 속도·주기성, 개폐 패턴 | Task 2 · Task 5 |
| AU 패턴 | AU12·25·26 활성도 및 주기성 | Task 2 · Task 5 |
| 동기화 | 음성-입모양 일관성 | Task 5 |
| 비대칭 | 좌우 비대칭 지수 및 진폭 비대칭 | Task 2 · Task 5 |

- MediaPipe·OpenFace·Py-Feat를 동일 영상에서 비교하여 Landmark 검출률과 흔들림 점검
- 조명, 안면 가림, 머리 자세, 프레임 유실을 포함한 Face QC 기준 및 SOP 초안 작성
- 임상 수집 전 소규모 촬영 리허설을 통해 실제 환경의 검출 성공률 확인
- 연구노트를 일별로 분리하여 정기 작성하고 작성자·책임자 서명 관리

> 연구노트 책임자: 강경훈 교수님 / 월 최소 4~5개 작성

## 결과물

- [최종 Benchmark PDF](../../output/pdf/pyfeat_testonly_benchmark.pdf)
- [AFLFP 결과 요약](../../paper/results/aflfp-test.md)
- [DISFA 결과 요약](../../paper/results/disfa-test.md)
- [실험 재현 방법](../../paper/README.md)
