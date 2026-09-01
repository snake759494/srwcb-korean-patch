# 간편 적용 설치 도구 (컴플리트 박스)

이 폴더의 소스로 릴리스의 easy-apply zip 을 구성합니다.
**최신: v0.11.51** — EX 오프닝 인용문 가독성 재수정과 제3차 엔딩·예고편·크레딧 그래픽을 포함한
제2차·제3차·EX·트레이닝 모드 컴플리트 박스 패치.

- `한글패치 적용하기.bat` — ASCII 런처(더블클릭). PowerShell 실행 정책을 우회해 `apply.ps1` 만 실행합니다.
- `apply.ps1` — 실제 적용 엔진(UTF-8 BOM). SHA-256 검증 → xdelta 패치 → 결과 검증 → `.cue` 생성.
- `사용법 - 먼저 읽어주세요.txt`, `xdelta3-정보.txt` — 배포용 안내문.

배포 zip 에는 위 파일들과 함께 `xdelta.exe`(제3자 GPL/오픈소스 도구)와
해당 버전의 `.xdelta` 패치가 포함됩니다.
`xdelta.exe` 는 라이선스상 저장소에 커밋하지 않습니다.

버전별 대상 패치:
- v0.11.51: `srwcb-second-third-ex-korean-v0.11.51.xdelta` (게임용 Galmuri14 픽셀 글꼴로 EX 인용문 가독성 재수정)
- v0.11.50: `srwcb-second-third-ex-korean-v0.11.50.xdelta` (EX 오프닝 인용문 가독성 재수정)
- v0.11.49: `srwcb-second-third-ex-korean-v0.11.49.xdelta` (EX 오프닝·제3차 엔딩/예고편 그래픽)
- v0.11.48: `srwcb-second-third-ex-korean-v0.11.48.xdelta` (제2차 페이즈 종료 문구·동적 숫자 겹침 수정)
- v0.11.47: `srwcb-second-third-ex-korean-v0.11.47.xdelta` (제2차 페이즈 UI 최종 반영 및 전체 패치)
- v0.11.46: `srwcb-second-third-ex-korean-v0.11.46.xdelta` (제2차·제3차·EX 전체, 컴플리트 박스 타이틀 메뉴 통일)
- v0.11.45: `srwcb-second-third-ex-korean-v0.11.45.xdelta` (제2차·제3차·EX 전체)
- v0.8.7: `srwcb-second-korean-v0.8.7.xdelta` (제2차 전체)
