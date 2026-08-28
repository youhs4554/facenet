# 범용 MetaHuman CLI · control path · progress · mannequin TDD 기록

작성일: 2026-08-27

## 범위

- Taro 명칭의 production CLI/helper를 범용 MetaHuman 명칭으로 전환하되 호환 wrapper 유지
- config → NVIDIA request → ACE capture → AnimSequence → MRQ → MP4 적용 경계 검증
- 실제 상태 기반 TTY/non-TTY progress와 JSONL event
- A2F-68로 직접 변형하는 clean triangulated Claire mannequin surface와 1920×1080 triptych

## RED

먼저 다음 실패 계약을 테스트에 고정했다.

- canonical CLI가 없고 legacy 명령이 deprecation wrapper가 아님
- face parameter가 설치 ACE 2.5 이름/범위를 검증하지 않음
- timecoded emotion/curve postprocess가 최종 MP4에 반영되지 않음
- progress TTY/non-TTY/never와 stdout 분리 계약이 없음
- mannequin zero/deformed geometry hash와 surface topology 계약이 없음

관련 테스트:

```text
test_a2f_generic_cli.py
test_a2f_progress.py
test_a2f_motion.py
test_a2f_mannequin.py
test_run_a2f_taro_official.py
```

## GREEN 구현

- `run-a2f-metahuman.py` canonical CLI와 legacy `os.execv` wrapper
- `a2f_metahuman_capture.py`, `a2f_metahuman_movie_pipeline_executor.py` + old import shims
- exact ACE 2.5 parameter registry와 strict motion config
- effective JSON을 run-owned AnimSequence 복제본에 52-curve bulk bake
- stderr progress + `progress-events.jsonl`
- Claire low-resolution blendshape basis와 공식 template topology를 사용한 software triangle surface renderer
- avatar + mannequin + curves 1920×1080 synchronized triptych

## 자동 검증

```bash
python3 -m pytest -q scripts/audio2face-metahuman/tests
# 114 passed + 6 subtests (최종 v3 default/lineage/master-clock 포함)

python3 -m py_compile \
  scripts/audio2face-metahuman/run-a2f-metahuman.py \
  scripts/audio2face-metahuman/a2f_motion.py \
  scripts/audio2face-metahuman/a2f_mannequin.py \
  scripts/audio2face-metahuman/a2f_progress.py
```

Unreal bulk helper build:

```text
.tools/audio2face3d/v3/generic-control-bulk-build.log
Result: Succeeded
```

## 실제 E2E

```text
.tools/audio2face3d/official-cli-runs/20260827-140813-generic-controls-bulk-final-e2e/
```

- v3 official inference: 218 frames × 68 curves
- pre-transform AnimSequence 보존, 별도 effective asset에 52 curves × 218 keys 적용
- MRQ: 실제 frame progress 0/109→109/109
- final avatar 및 diagnostic triptych: H.264/AAC, 30 fps, 109 frames, A/V start 0 ms, full decode PASS
- mannequin raw/effective: H.264 640×540, 109 frames, geometry/frame sample SHA가 서로 동적
- 사용자 UnrealEditor PID 1224942 유지

시각 확인:

```text
.tools/audio2face3d/official-cli-runs/20260827-140813-generic-controls-bulk-final-e2e/diagnostic-triptych-frame-1.633.png
```

## 정직한 경계

surface는 NVIDIA Claire evaluation-only sample의 solver basis/topology다. 선택한 MetaHuman mesh 또는 v3 direct geometry는 아니다. 설치 ACE 2.5가 최종 render에서 소비하는 52 curve만 bulk bake하며 extended tongue 16개는 artifact/mannequin에만 보존한다.

## content sync 결함 수정과 readable panel

사용자 피드백 뒤 stream timestamp가 아니라 영상 내용으로 재현했다.

```text
기존 140813 MP4: rendered avatar +4 frames / +133.333 ms
correlation: 0.951, status: misaligned
```

`test_a2f_sync.py`를 먼저 추가해 존재하지 않는 timeline/lag API로 RED 4 errors를 확인했다. 첫 audio-zero 가설은 실제 run `20260827-142513-sync-audio-zero-e2e`에서 낮은 상관과 큰 지연을 만들어 기각했다. 이어 verified post-render correction 테스트를 먼저 RED 3 failures로 만든 뒤 구현했다.

최종 GREEN run `20260827-143129-sync-content-final-e2e`:

- pre-sync: +5 frames / +166.667 ms, correlation 0.940
- corrected: 0 frames / 0 ms, correlation 0.942
- 원본 `*-pre-sync.mp4` 보존, audio bitstream unchanged
- corrected final/triptych H.264/AAC, 109 frames, start delta 0 ms, full decode PASS

수치 패널은 `test_compact_triptych_panel_has_readable_type_and_reduced_hierarchy`와 dynamic-frame test를 먼저 RED 2 failures로 확인했다. 후속 사용자 피드백으로 `test_compact_curve_rows_are_sorted_by_current_effective_value`를 추가하고, emotion 미표시 계약과 함께 RED 2 failures를 다시 확인했다. 최종 GREEN 구현은 640×540 native layout, 최소 16 px type, curve 18 px, 현재 effective 값 내림차순 8개 curve, 68-curve heat strip, emotion 표시 0개를 보장한다. 기존 상세 시각화와 emotion JSON/CSV는 삭제하지 않는다.

artifact smoke:

```text
.tools/audio2face3d/official-cli-runs/20260827-143129-sync-content-final-e2e/
  motion-artifacts/readable-motion-panel-v2.mp4
  taro-a2f-sync-content-final-e2e-final-readable-triptych-v2.mp4
  readable-triptych-v2-frame-1.633.png
  readability-verification.json
```

최신 sorted/no-emotion artifact:

```text
.tools/audio2face3d/official-cli-runs/20260827-144232-default-v23-readable-sync-final/
  motion-artifacts/readable-motion-panel-sorted-v3.mp4
  taro-a2f-default-v23-readable-sync-final-sorted-no-emotion-v3.mp4
  sorted-no-emotion-v3-frame-1.633.png
  readability-sorted-v3-verification.json
```

기본 모델을 v3로 전환하기 전 당시의 무옵션 v2.3 회귀 E2E도 `20260827-144232-default-v23-readable-sync-final`에서 통과했다. 이는 historical v2 characterization이지 현재 canonical 기본값이 아니다. 현재 v2는 explicit opt-in이며, 최신 v3 default 증거는 `audio2face-v3-default-lineage-sync.tdd.md`를 참조한다.

코드 리뷰에서 발견된 추가 RED/GREEN:

- `mode=baseline` + non-identity postprocess가 허용된 뒤 무시되던 재현 테스트를 RED로 추가하고, 이제 `mode=enhanced` 사용을 요구한다.
- v3 label을 52000 v2 service에 연결할 수 있던 cross-wire 테스트와 custom endpoint provenance 테스트를 RED로 추가했다. 알려진 로컬 포트는 모델에 bind하고, custom/remote는 local engine hash를 제외한 `unattested`로 기록한다.
