# Audio2Face canonical 기본 모델 v3.0 전환 안내

적용일: 2026-08-27

## 변경

`run-a2f-metahuman.py`와 legacy compatibility wrapper의 no-option 모델이 `v2.3-regression`에서 `v3.0-diffusion`으로 변경됐다.

```text
no option → v3.0-diffusion → multi_v3.2 → 127.0.0.1:52100
```

이는 behavioral breaking change다. v3 service가 없거나 model/cadence 검증이 실패해도 v2로 자동 fallback하지 않는다.

## legacy v2 opt-in

```bash
scripts/audio2face-metahuman/run-a2f-metahuman.py input.wav \
  --a2f-model v2.3-regression
```

이 명령은 기존 `claire_v2.3.1`/52000 service와 artifacts를 그대로 사용한다.

## resume

- model 옵션을 생략한 old v2 resume: source manifest의 v2/52000 상속
- model 옵션을 생략한 v3 resume: source manifest의 v3/52100 상속
- resume source와 explicit model/endpoint가 다름: 거부
- 다른 model로 새 inference가 필요함: `--resume`을 제거하고 새 run 생성

## 파일명

- model: `v23-regression` 또는 `v30-diffusion`
- layout: `layout-v3` 같은 별도 token

과거 `...sorted-no-emotion-v3.mp4`의 `v3`는 layout revision이었고 실제 manifest는 v2.3이다. 신규 파일명에서는 이 모호한 표기를 사용하지 않는다.

## 복구

v3 health failure:

```bash
scripts/audio2face-metahuman/start-a2f-v3-diffusion.sh
```

그 뒤 동일 no-option 명령을 다시 실행한다. 자동 v2 fallback은 없다.
