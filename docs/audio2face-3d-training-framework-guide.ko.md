# NVIDIA Audio2Face-3D Training Framework 로컬 사용 설명서

작성일: 2026-08-26
대상 서버: `aim-dev-server` (Ubuntu 24.04.4 LTS)

> **보존된 이전 학습 경로:** 2026-08-26 요구사항이 pretrained 무학습 데모로 변경되어, 새 학습은 수행하지 않습니다. 아래 학습 절차는 이전 작업 기록으로만 남겨 두었으며, 현재 실행 설명서는 [Audio2Face-3D pretrained NIM 데모 사용 설명서](audio2face-3d-pretrained-demo-guide.ko.md)입니다.

이 문서는 이 저장소에 설치한 NVIDIA Audio2Face-3D Training Framework를 처음부터 확인하고, Claire 예제 데이터로 전처리, 학습, 배포, 추론까지 실행하는 순서를 설명합니다.

## 1. 먼저 알아둘 점

Audio2Face-3D Training Framework는 음성에서 얼굴 애니메이션 모델을 학습하는 도구입니다. 웹 브라우저에서 바로 얼굴이 움직이는 데모는 포함하지 않습니다. 기본 시연 흐름은 다음과 같습니다.

1. Claire 음성과 3D 애니메이션 캐시를 전처리합니다.
2. 음성-얼굴 애니메이션 모델을 학습합니다.
3. 학습 모델을 배포 형식으로 변환합니다.
4. 음성을 입력해 NumPy 배열 또는 Maya 캐시 형태의 얼굴 애니메이션을 생성합니다.
5. 필요하면 Maya-ACE에서 캐시를 캐릭터에 연결해 시각적으로 확인합니다.

공식 자료:

- [Audio2Face-3D Training Framework](https://github.com/NVIDIA/Audio2Face-3D-Training-Framework)
- [Claire 예제 데이터셋](https://huggingface.co/datasets/nvidia/Audio2Face-3D-Dataset-v1.0.0-claire)
- [Maya-ACE 플러그인](https://github.com/NVIDIA/Maya-ACE)

## 2. 이 서버에 설치된 구성

| 항목 | 값 |
| --- | --- |
| 프레임워크 버전 | `v1.0.1` |
| 고정 커밋 | `112c5eb3408afd065ac8974b2c6ea9ab0e3965c6` |
| 프레임워크 경로 | `/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/Audio2Face-3D-Training-Framework` |
| 데이터셋 경로 | `/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/datasets` |
| 실행 결과 경로 | `/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/workspace` |
| Docker 이미지 | `audio2face-framework-env:latest` |
| 이미지 ID | `sha256:49486a3a792c2ff0c1049d51201e786a2a7cf9c954f3deb809a3777c5d76ba83` |
| 이미지 크기 | 약 18.04 GB |
| 컨테이너 환경 | Ubuntu 22.04, Python 3.10, CUDA 12.8.1, PyTorch 2.7.1+cu128 |

설치 본체와 데이터, 학습 결과는 `.tools/` 아래에 있으며 이 프로젝트의 Git 추적 대상이 아닙니다. 연구 코드와 대용량 모델 산출물이 섞이지 않도록 의도적으로 분리했습니다.

## 3. 현재 검증 결과

다음 항목은 2026-08-26에 실제로 확인했습니다.

- Docker 이미지 빌드 성공
- NVIDIA Container Runtime에서 GPU 2장 인식 성공
- `NVIDIA RTX A4500` 20 GB, `Quadro RTX 5000` 16 GB 인식 성공
- 두 GPU 각각에서 PyTorch CUDA 텐서 연산 성공
- CuPy에서 CUDA 장치 2개 인식 성공
- `audio2face` 전처리, diffusion/regression 학습, 배포, 추론 모듈 import 성공
- 네 가지 예제 설정(`example-diffusion`, `example-diffusion-min`, `example-regression`, `example-regression-min`) 로딩 성공
- 호스트 실행 래퍼의 CLI 인자 파싱 성공

Hugging Face CLI 로그인은 `user=hossay`로 확인됐지만, Claire 데이터셋에 대한 계정 승인은 아직 없습니다. 실제 clone 검사는 `403`과 함께 `you are not in the authorized list`를 반환했습니다. 따라서 아래 6장의 웹 라이선스 동의가 끝나기 전에는 Claire 전처리, 학습, 배포, 추론을 실행할 수 없습니다.

현재 NVIDIA 드라이버는 `580.173.02`입니다. NVIDIA가 이 프레임워크에 명시한 Linux 지원 범위는 `575.57`부터 `579.x`까지이므로 공식 지원 범위보다 높습니다. 이 서버에서는 CUDA와 실제 텐서 연산이 성공했지만, 향후 프레임워크 오류가 발생하면 드라이버 버전도 원인 후보로 확인해야 합니다. 시스템 전체에 영향을 주는 드라이버 변경은 자동으로 수행하지 않았습니다.

공식 Dockerfile이 설치한 Poetry 도구 의존성에는 2026년 시점의 최신 `virtualenv`/`cryptography`와 프레임워크 lockfile 사이의 `pip check` 경고가 있습니다. Audio2Face 런타임 모듈 import와 CUDA 연산에는 영향을 주지 않았으며, 공식 lockfile을 임의 변경하지 않기 위해 그대로 유지했습니다.

## 4. 매번 터미널에서 사용할 경로 설정

새 터미널을 열 때 아래 세 줄을 먼저 실행하면 긴 경로를 반복해서 입력하지 않아도 됩니다.

```bash
A2F_INSTALL_ROOT="/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d"
A2F_FRAMEWORK_ROOT="$A2F_INSTALL_ROOT/Audio2Face-3D-Training-Framework"
A2F_WORKSPACE_ROOT="$A2F_INSTALL_ROOT/workspace"
```

프레임워크 폴더로 이동합니다.

```bash
cd "$A2F_FRAMEWORK_ROOT"
```

설치 커밋과 환경 경로를 확인합니다.

```bash
git rev-parse HEAD
sed -n '1,20p' .env
docker image inspect audio2face-framework-env:latest \
  --format 'ID={{.Id}} SIZE={{.Size}} CREATED={{.Created}}'
```

## 5. 즉시 실행할 수 있는 GPU 스모크 데모

Claire 데이터가 없어도 설치된 프레임워크와 GPU가 작동하는지는 바로 확인할 수 있습니다.

```bash
docker run --rm --gpus all \
  -v "$A2F_FRAMEWORK_ROOT":/framework \
  -w /framework \
  audio2face-framework-env:latest \
  python -c 'import torch, cupy, audio2face; print("torch:", torch.__version__); print("cuda:", torch.version.cuda); print("gpu count:", torch.cuda.device_count()); print("gpus:", [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]); print("tensor sum:", float((torch.ones(1024, device="cuda:0") * 2).sum()))'
```

정상이라면 `cuda: 12.8`, `gpu count: 2`, GPU 이름 두 개, `tensor sum: 2048.0`이 출력됩니다. CUDA 컨테이너의 라이선스 안내 문구와 PyTorch `FutureWarning`은 오류가 아닙니다.

## 6. Claire 데이터셋 접근 승인과 로그인

Claire 데이터셋은 1 GB 미만이지만 gated 데이터입니다. NVIDIA Audio2Face Sample Data License에 직접 동의하고 연락처 공유를 승인한 Hugging Face 계정만 내려받을 수 있습니다. 이 법적 동의는 계정 소유자가 직접 해야 합니다.

1. 브라우저에서 [Claire 데이터셋 페이지](https://huggingface.co/datasets/nvidia/Audio2Face-3D-Dataset-v1.0.0-claire)를 엽니다.
2. Hugging Face에 로그인합니다.
3. 라이선스를 읽고 동의할 경우 `Agree and Access`를 누릅니다.
4. [Access Tokens](https://huggingface.co/settings/tokens)에서 읽기 권한 토큰을 준비합니다.
5. 이 서버의 로컬 터미널에서 다음 명령을 실행하고 토큰을 입력합니다.

```bash
hf auth login --add-to-git-credential
```

토큰은 채팅, 문서, Git 커밋에 붙여 넣지 마십시오. 로그인 상태만 확인합니다.

```bash
hf auth whoami
```

## 7. Claire 데이터셋 다운로드

라이선스 승인과 로그인이 끝난 뒤 실행합니다.

```bash
cd "$A2F_INSTALL_ROOT/datasets"
git lfs install
git clone https://huggingface.co/datasets/nvidia/Audio2Face-3D-Dataset-v1.0.0-claire
```

이미 저장소만 받아지고 대용량 파일이 빠졌다면 다음 명령으로 LFS 파일을 다시 받습니다.

```bash
git -C Audio2Face-3D-Dataset-v1.0.0-claire lfs pull
git -C Audio2Face-3D-Dataset-v1.0.0-claire lfs fsck
```

필수 폴더를 확인합니다.

```bash
test -d "$A2F_INSTALL_ROOT/datasets/Audio2Face-3D-Dataset-v1.0.0-claire/data/claire/audio" && echo "audio: OK"
test -d "$A2F_INSTALL_ROOT/datasets/Audio2Face-3D-Dataset-v1.0.0-claire/data/claire/cache" && echo "cache: OK"
find "$A2F_INSTALL_ROOT/datasets/Audio2Face-3D-Dataset-v1.0.0-claire/data/claire" \
  -maxdepth 2 -type d | sort
```

## 8. 공식 전체 데모: 전처리부터 추론까지

아래는 NVIDIA README의 `example-diffusion` 흐름입니다. 최초 학습은 GPU에 따라 보통 약 30~40분이 걸립니다.

### 8.1 전처리

```bash
cd "$A2F_FRAMEWORK_ROOT"
python3 run_preproc.py example-diffusion claire
```

끝부분에 다음과 비슷한 값이 출력됩니다.

```text
Preproc Run Name Full: 260826_123456_example
```

값을 잊었다면 가장 최근 전처리 폴더를 확인합니다.

```bash
ls -1dt "$A2F_WORKSPACE_ROOT"/output_preproc/* | head
```

### 8.2 전처리 실행 이름 연결

다음 파일을 편집기로 엽니다.

```bash
nano "$A2F_FRAMEWORK_ROOT/configs/example-diffusion/config_train.py"
```

`PREPROC_RUN_NAME_FULL`에서 자리표시자를 방금 생성된 실제 이름으로 바꿉니다.

```python
PREPROC_RUN_NAME_FULL = {
    "claire": "260826_123456_example",
}
```

`260826_123456_example`은 예시이므로 본인의 실제 출력값을 사용해야 합니다. 저장은 `Ctrl+O`, Enter, 종료는 `Ctrl+X`입니다.

### 8.3 학습

```bash
cd "$A2F_FRAMEWORK_ROOT"
python3 run_train.py example-diffusion
```

학습 로그에는 남은 예상 시간이 표시됩니다. 완료 후 다음과 비슷한 이름이 출력됩니다.

```text
Training Run Name Full: 260826_130000_example-diffusion
```

가장 최근 학습 폴더는 다음과 같이 확인합니다.

```bash
ls -1dt "$A2F_WORKSPACE_ROOT"/output_train/* | head
```

이후 명령에서 사용할 실제 이름을 변수로 저장합니다.

```bash
TRAINING_RUN_NAME_FULL="260826_130000_example-diffusion"
```

### 8.4 배포 패키지 생성

```bash
cd "$A2F_FRAMEWORK_ROOT"
python3 run_deploy.py example-diffusion "$TRAINING_RUN_NAME_FULL"
```

결과는 다음 폴더에 생깁니다.

```bash
find "$A2F_WORKSPACE_ROOT/output_deploy/$TRAINING_RUN_NAME_FULL" \
  -maxdepth 2 -type f | sort | head -50
```

### 8.5 음성 추론

기본 설정은 Claire 데이터의 `eg1_neutral.wav`를 입력으로 사용합니다.

```bash
cd "$A2F_FRAMEWORK_ROOT"
python3 run_inference.py example-diffusion "$TRAINING_RUN_NAME_FULL"
```

생성 파일을 확인합니다.

```bash
find "$A2F_WORKSPACE_ROOT/output_inference/$TRAINING_RUN_NAME_FULL" \
  -type f -printf '%TY-%Tm-%Td %TH:%TM  %10s  %p\n' | sort
```

`configs/example-diffusion/config_inference.py`에서 다음 값을 조절할 수 있습니다.

- `AUDIO_PATH`: 컨테이너 안에서 보이는 `/datasets/...` 입력 음성 경로
- `INFERENCE_OUTPUT_ROOT`: 기본값 `/workspace/output_inference`
- `OUTPUT_MAYA_CACHE`: Maya `.mc` 캐시 출력 여부
- `OUTPUT_NPY_FILE`: 원시 NumPy 애니메이션 배열 출력 여부
- `TIMESTEP_RESPACING`: diffusion 추론 속도와 품질의 균형

설정을 바꿀 때는 한 번에 하나씩 바꾸고, 동일한 학습 실행 이름으로 추론을 다시 실행해 결과를 비교하는 것이 좋습니다.

## 9. 더 가벼운 구성으로 먼저 확인하기

전체 얼굴 부가 데이터 없이 음성과 skin cache 중심으로 먼저 확인하려면 `example-regression-min` 구성을 사용할 수 있습니다. 이 구성은 데이터 요구사항이 더 적고 학습 epoch도 diffusion-min보다 적지만, 실행 시간과 품질은 하드웨어와 데이터에 따라 달라집니다.

```bash
cd "$A2F_FRAMEWORK_ROOT"
python3 run_preproc.py example-regression-min claire
```

생성된 전처리 이름을 다음 파일의 `PREPROC_RUN_NAME_FULL["claire"]`에 넣습니다.

```text
configs/example-regression-min/config_train.py
```

그다음 순서대로 실행합니다.

```bash
python3 run_train.py example-regression-min
python3 run_deploy.py example-regression-min <실제_TRAINING_RUN_NAME_FULL>
```

현재 upstream의 `runners/run_inference.py`는 regression 네트워크에 대해 `NotImplementedError`를 발생시킵니다. 따라서 첫 end-to-end Python 추론 시연은 지원 경로가 완비된 `example-diffusion` 구성을 권장합니다.

## 10. Maya에서 시각적으로 보기

Python 추론 결과는 수치 배열이나 Maya 캐시입니다. 캐릭터에 적용된 얼굴 움직임을 보려면 Maya와 Maya-ACE가 필요합니다.

1. [NVIDIA Maya-ACE](https://github.com/NVIDIA/Maya-ACE)의 지원 Maya 버전과 설치 방법을 확인합니다.
2. Claire 데이터셋의 참조 장면을 엽니다.

```text
Audio2Face-3D-Dataset-v1.0.0-claire/data/claire/geom/fullface/a2f_maya_scene.mb
```

3. `output_deploy/<TRAINING_RUN_NAME_FULL>`의 모델을 Maya-ACE에 로드합니다.
4. `output_inference/<TRAINING_RUN_NAME_FULL>`의 Maya 캐시를 연결하거나 Maya-ACE에서 직접 음성 추론을 실행합니다.

Maya는 별도 상용 소프트웨어이며 이 서버의 headless Docker 환경에는 설치하지 않았습니다.

## 11. 자주 발생하는 문제

### 데이터셋 clone에서 사용자 이름을 묻거나 401/403 오류가 납니다

대부분 라이선스 미동의 또는 Hugging Face 인증 문제입니다.

```bash
hf auth whoami
hf auth login --add-to-git-credential
```

그 뒤 데이터셋 웹페이지에서 `You have been granted access` 상태인지 확인합니다.

### `Please update PREPROC_RUN_NAME_FULL` 오류가 납니다

`configs/<사용할 구성>/config_train.py`의 `XXXXXX_XXXXXX_example` 자리표시자를 실제 `output_preproc` 폴더 이름으로 바꾸지 않은 경우입니다.

### Docker 이미지가 없다고 나옵니다

```bash
cd "$A2F_FRAMEWORK_ROOT"
./docker/build_docker.sh
```

최초 빌드는 CUDA/PyTorch 이미지를 내려받고 약 18 GB 이미지를 생성하므로 시간이 걸립니다.

### Docker 안에서 GPU가 보이지 않습니다

```bash
nvidia-smi
docker info --format '{{json .Runtimes}}'
docker run --rm --gpus all audio2face-framework-env:latest nvidia-smi
```

Docker runtime 목록에 `nvidia`가 없으면 NVIDIA Container Toolkit 설정을 확인해야 합니다. 이 서버에서는 이미 `nvidia` runtime과 GPU 2장을 확인했습니다.

### CUDA 오류가 반복됩니다

이 서버의 드라이버 `580.173.02`는 실제 CUDA 테스트에는 성공했지만 NVIDIA의 명시적 지원 범위 `575.57`~`579.x` 밖입니다. 오류 로그에 driver/runtime mismatch가 보이면 지원 범위의 드라이버가 필요한지 시스템 관리자와 검토하십시오. 드라이버 변경 전에는 다른 GPU 작업에 미치는 영향과 복구 계획을 먼저 확인해야 합니다.

### `pip check`가 Poetry 도구 패키지 충돌을 보고합니다

공식 Dockerfile은 Poetry를 먼저 설치한 뒤 프레임워크 lockfile을 전역 환경에 적용합니다. 2026년의 최신 Poetry 하위 패키지 일부와 2025년 lockfile 사이에서 경고가 생기지만, Audio2Face 런타임 import와 GPU 연산은 통과했습니다. 임의로 패키지를 업그레이드하면 NVIDIA가 고정한 학습 환경이 달라지므로, 실제 런타임 오류가 없는 한 lockfile을 유지하십시오.

## 12. 결과 폴더 한눈에 보기

```text
.tools/audio2face3d/
├── Audio2Face-3D-Training-Framework/  # NVIDIA 소스와 .env
├── datasets/
│   └── Audio2Face-3D-Dataset-v1.0.0-claire/
└── workspace/
    ├── output_preproc/                # 전처리 산출물
    ├── output_train/                  # 체크포인트, ONNX 등 학습 산출물
    ├── output_deploy/                 # Maya-ACE용 배포 패키지
    └── output_inference/              # .npy 또는 .mc 추론 결과
```

작업을 다시 시작할 때는 `output_preproc`와 `output_train`의 가장 최근 폴더 이름을 먼저 확인하십시오. 이름은 `YYMMDD_HHMMSS_<RUN_NAME>` 형식이라 실행 이력을 구분하기 쉽습니다.

## 13. 재검증 체크리스트

- [ ] Claire 데이터셋 페이지에서 라이선스를 직접 확인하고 접근 승인
- [x] `hf auth whoami` 성공 (`user=hossay`)
- [ ] 데이터셋 clone 및 `git lfs fsck` 성공
- [ ] `audio`와 `cache` 폴더 확인
- [x] GPU 스모크 데모 성공
- [ ] 전처리 성공 및 `PREPROC_RUN_NAME_FULL` 기록
- [ ] 학습 성공 및 `TRAINING_RUN_NAME_FULL` 기록
- [ ] 배포 폴더 생성 확인
- [ ] 추론 출력 `.npy` 또는 `.mc` 확인
- [ ] 필요 시 Maya-ACE에서 캐릭터 애니메이션 확인
