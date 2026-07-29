# Background Studio Python 1.2.0

## 핵심 변경

- 밝기·대비·채도·색온도·색조·불투명도 편집
- 마스크 임계값·페더·확장/축소
- 회전·좌우/상하 반전과 1:1·4:5·16:9 캔버스
- 고대비·포스터·세피아·반전·연필선 필터
- API와 CLI의 동일한 고급 편집 파라미터
- Python 설치 없이 실행하는 Windows x64 EXE와 SHA-256 파일

## Windows 실행 파일

ZIP을 풀고 `BackgroundStudio-Python.exe`를 실행합니다. 로컬 전용 API가
준비되면 실행 창에 주소가 표시됩니다. 첫 AI 처리에서는 모델 다운로드가
발생할 수 있습니다. 동영상 처리는 시스템 FFmpeg가 필요합니다.

## 확인 결과

- Ruff 통과
- Pytest 12개 통과
- 패키지 EXE GUI 실행과 `/healthz` 응답 확인
- 패키지 EXE에서 고급 옵션을 적용한 1122×1122 RGBA PNG 생성 확인
- 창 닫기 후 로컬 포트 해제 확인
