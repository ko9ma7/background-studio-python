# Background Studio Python 1.3 사용 설명서

## Windows GUI

1. GitHub Releases에서 `BackgroundStudio-Python-v1.3.0-win-x64.zip`을 받습니다.
2. 압축을 완전히 풀고 `BackgroundStudio-Python.exe`를 실행합니다.
3. `파일 추가`로 이미지나 동영상을 대기열에 넣습니다.
4. 배경, 필터·외곽, 위치·크기, 고급, 저장 탭을 설정합니다.
5. `대기열 전체 변환`을 누릅니다.

결과는 기본적으로 `사진\Background Studio Python`에 자동 저장되고 결과
목록에 남습니다. 잘못 추가한 항목은 선택 삭제, 새 작업은 전체 초기화를
사용합니다. 처리 중에도 다른 항목과 편집값을 준비할 수 있습니다.

첫 변환에서는 선택한 rembg 모델을 사용자 캐시에 내려받습니다. 동영상 처리
때는 검증된 FFmpeg를 앱 자체 폴더에 준비하므로 시스템 PATH가 필요하지
않습니다.

## 형식과 편집

- 이미지 입력: PNG, JPEG, WebP, BMP, TIFF
- 이미지 출력: PNG, JPEG, WebP, BMP, TIFF, SVG
- 영상 출력: MP4, WebM, MOV, GIF
- 투명 영상: WebM VP9 alpha, MOV ProRes 4444

마스크, 외곽선, 코믹·연필선 필터, 중앙 정렬, 크기·위치, 회전·반전,
캔버스, 색 보정을 조합할 수 있습니다. 중요한 결과는 확대해 머리카락,
반투명 물체, 모션 블러 경계를 직접 확인하세요.

## CLI와 API

반복 폴더 작업은 `background-studio` CLI, 사내 서비스 연동은 FastAPI를
사용합니다. API 문서는 소스 실행 후 `http://127.0.0.1:8000/docs`에서
확인합니다. 인터넷 공개 전에는 인증, 요청 제한, 악성 파일 검사, TLS,
외부 작업 큐와 저장소를 추가해야 합니다.

## 세 가지 버전 선택

- 설치 없는 브라우저 작업: [Web](https://github.com/ko9ma7/background-studio-web)
- Windows 전용 GUI: [C# WPF](https://github.com/ko9ma7/background-studio-wpf)
- GUI와 CLI/API를 함께 사용: 현재 Python 버전
