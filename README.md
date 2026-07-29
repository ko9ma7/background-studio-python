# Background Studio · Python 1.2

이미지와 동영상의 배경 제거, 외곽·마스크 추출, 색 보정, 위치·캔버스 편집을
로컬에서 실행하는 FastAPI + CLI 프로젝트입니다. Windows용 실행 파일도
제공하므로 Python을 설치하지 않고 로컬 API를 열 수 있습니다.

## 제공 기능

- 이미지: PNG/JPEG/WebP/BMP/TIFF 입력과 PNG/JPEG/WebP/BMP/TIFF/SVG 출력
- 가장자리: rembg 알파 매팅·마스크 후처리 옵션
- 그림자: 흐림, 불투명도, X/Y 오프셋
- 모델 선택: U2Net, ISNet, BiRefNet 계열 rembg 세션
- 전문 편집: 중앙 정렬·크기·X/Y 위치, 회전·반전, 캔버스 비율
- 색 보정: 밝기·대비·채도·색온도·색조·피사체 불투명도
- 마스크 보정: 임계값·페더·확장/축소, 마스크·외곽선 단독 레이어
- 필터: 밝게·선명하게·웜·쿨·흑백·코믹·고대비·포스터·세피아·반전·연필선
- 동영상: 길이 제한 없는 MP4/WebM/MOV/GIF, 진행률, 원본 오디오 유지
- 고급 선택: SAM 3 텍스트 프롬프트 마스크 엔드포인트(별도 설치·라이선스)
- 운영: Docker, 상태 확인, 업로드 제한, 만료 작업 정리, CI

모든 기본 처리는 내 PC/서버에서 실행됩니다. 외부 AI API로 파일을 보내지
않습니다.

## 빠른 시작

Python 3.11~3.13과 [uv](https://docs.astral.sh/uv/)를 권장합니다.

```bash
uv sync --extra dev
uv run uvicorn background_studio.api:app --reload
```

브라우저에서 `http://127.0.0.1:8000/docs`를 열면 API를 직접 시험할 수
있습니다. 첫 실행에서는 선택한 rembg 모델이 사용자 캐시로 내려받아집니다.

Docker에는 FFmpeg가 포함됩니다.

```bash
docker compose up --build
```

## Windows EXE

[GitHub Releases](https://github.com/ko9ma7/background-studio-python/releases)에서
`BackgroundStudio-Python-v1.2.0-win-x64.zip`을 내려받아 압축을 풀고
`BackgroundStudio-Python.exe`를 실행합니다.

- 실행 창이 로컬 API를 준비한 뒤 `http://127.0.0.1:8765/docs`를 엽니다.
- 첫 처리 때 선택한 rembg 모델을 사용자 캐시에 내려받습니다.
- 종료 버튼이나 창 닫기를 누르면 API 서버와 사용 포트도 함께 닫힙니다.
- 동영상은 FFmpeg가 별도로 필요합니다. 이미지 처리와 편집은 EXE만으로
  실행됩니다.

릴리스 ZIP 옆의 `.sha256` 파일로 다운로드 무결성을 확인할 수 있습니다.
소스에서 직접 만들려면 Windows PowerShell에서 다음을 실행합니다.

```powershell
uv sync --extra dev
.\scripts\build-windows.ps1
```

## CLI

```bash
uv run background-studio image input.jpg output.png \
  --mode color --color "#f5f5f5" --alpha-matting \
  --foreground-filter comic --auto-center --subject-scale 0.9 \
  --brightness 1.1 --contrast 1.15 --saturation 1.2 \
  --mask-feather 0.12 --canvas-aspect square

uv run background-studio image input.jpg output.png \
  --mode image --background studio.jpg

uv run background-studio image input.jpg outline.svg \
  --render-mode outline --auto-center --outline-width 4

uv run background-studio video input.mp4 output.webm \
  --mode transparent --max-dimension 1280

uv run background-studio video input.mp4 output.mp4 \
  --mode blur --blur-radius 22
```

동영상 CLI는 시스템 FFmpeg가 필요합니다. Docker에는 FFmpeg가 포함됩니다.
투명 동영상은 WebM(VP9 alpha) 또는 MOV(ProRes 4444), 일반 결과는
MP4/WebM/MOV/GIF를 사용할 수 있습니다.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | 엔진·FFmpeg 상태 |
| POST | `/v1/images/remove` | 이미지 분리와 배경 편집 |
| POST | `/v1/images/concept-mask` | 선택형 SAM 3 개념 마스크 |
| POST | `/v1/videos/remove` | 동영상 작업 생성 |
| GET | `/v1/jobs/{id}` | 진행률과 오류 |
| GET | `/v1/jobs/{id}/download` | 완성 파일 |

예시:

```bash
curl -o result.png \
  -F "file=@input.jpg" \
  -F "mode=color" \
  -F "color=#ffffff" \
  -F "alpha_matting=true" \
  http://127.0.0.1:8000/v1/images/remove
```

## SAM 3 선택형 엔진

SAM 3는 “사람”, “노란 자동차”처럼 개념을 지정해 마스크를 얻는 고급
경로입니다. 848M 파라미터 모델이라 기본 배경 제거보다 훨씬 무겁고, Meta의
별도 SAM License가 적용됩니다. 이 저장소는 SAM 3 코드·가중치를 자동으로
설치하거나 재배포하지 않습니다.

공식 저장소의 설치 안내를 따라 SAM 3를 별도로 설치하고 라이선스를 확인한
환경에서만 `/v1/images/concept-mask`가 활성화됩니다.

## 운영 전에 꼭 확인할 점

- 이 기본 작업 큐는 단일 프로세스용입니다. 여러 서버 인스턴스에서는 Redis
  같은 큐와 S3 호환 저장소로 교체하세요.
- 인터넷에 공개할 때는 인증, 요청 횟수 제한, 악성 파일 검사, TLS, 프록시
  업로드 제한을 추가해야 합니다.
- 사람·고객·저작물이 포함된 미디어는 처리 권한과 공개 동의를 확인하세요.
- 결과 가장자리는 머리카락, 반투명 물체, 모션 블러, 복잡한 그림자에서
  흔들릴 수 있습니다. 중요한 작업은 프레임을 직접 검수하세요.
- EXE 시작 직후 AI 모듈을 불러오는 동안 수 초가 걸릴 수 있습니다. 창의
  `실행 중` 문구가 표시된 뒤 API 문서를 여세요.

## 개발

```bash
uv run ruff check .
uv run pytest --cov=background_studio
docker build -t background-studio-python:test .
```

설계와 라이선스 판단은 [`docs/architecture.md`](docs/architecture.md),
[`docs/research-matrix.md`](docs/research-matrix.md),
[`docs/pro-editing-guide.md`](docs/pro-editing-guide.md),
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)에 정리했습니다.

## License

프로젝트 코드는 MIT입니다. rembg 모델, FFmpeg 빌드, SAM 3 등 외부 구성요소는
각자의 조건을 따릅니다.
