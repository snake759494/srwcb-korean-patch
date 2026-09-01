# v0.11.52 — 제2차·EX 선택 후 이탈 경로 재검증 및 제3차 상태 분석 보강

## 변경 내용

GitHub 열린 이슈 [#38](https://github.com/snake7594/srwcb-korean-patch/issues/38)과
제3차 라스트 배틀 이슈 [#20](https://github.com/snake7594/srwcb-korean-patch/issues/20)을
제2차·제3차·EX의 공통 실행 경로와 대조해 다시 검증했습니다.

### #38 — 잘못된 CUE를 만드는 간편 적용기 차단

이전 `easy-apply/apply.ps1`은 Track 2가 없어도 Track 1 패치를 끝낸 뒤 Track 2를
참조하는 CUE를 만들었습니다. 이 상태는 에뮬레이터의 디스크 TOC가 완성되지 않아
제2차·EX 선택 후 이탈처럼 보일 수 있습니다. 실제 검증에서도 Track 2 없이 CUE를
열면 RetroArch가 잘못된 TOC로 중단했고, 같은 Track 2를 함께 둔 CUE는 Sony BIOS와
게임 부팅까지 진행했습니다.

이번 버전은 다음을 적용합니다.

- Track 1을 패치하기 전에 원본 Track 2 파일의 존재를 확인합니다.
- Track 2 SHA-256을 `2fbf5a94ffc8b475741529c4a95d580c937ca37db31db227e0d6c7a917a1e95f`로
  검증합니다.
- 누락·오류 Track 2에서는 출력 파일이나 잘못된 CUE를 만들지 않고 중단합니다.
- 제2차·제3차·EX 공통 프런트엔드의 선택지 레코드는 기존 검증대로 제어 바이트와
  포인터를 보존합니다. 새 이미지 바이너리 변경은 없습니다.

따라서 #38은 v0.11.52로 Track 2를 같은 폴더에 둔 뒤 제2차와 EX를 다시 선택해
확인해 주세요. 사용자의 실제 세이브스테이트에서도 계속 이탈하면 그 상태 파일과
에뮬레이터 로그가 추가로 필요하며, 확인 전까지 이슈를 닫지 않습니다.

### #20 — DuckStation 세이브스테이트 분석 도구 복구

제3차 라스트 배틀의 정적 C_SMAP·EFFECT·STR·Track 1 검색에서는 문제의 동적 한 줄을
찾지 못했습니다. 이 줄은 일반 번역 레코드가 아니라 실행 중 조합되는 자산일 가능성이
높으므로, 관련 최종전 상태 없이 게임 바이너리에 추측 패치를 넣지 않았습니다.

대신 `tools/graphics/savestate_vram.py`가 특정 작업 환경에만 있던
`compression.zstd` import에 묶이지 않도록, 표준 `zstandard` API를 자동으로
사용하는 폴백을 추가했습니다. 저장소에 포함된 `23화세이브` 상태로 실제 검증한
결과는 zstd 프레임 2개, `GPU-VRAM` 1,049,600바이트, VRAM PNG 5개 생성입니다.
다만 이 상태들은 해당 동적 라인의 최종전 상태가 아니므로 #20은 열어 둡니다.

## 변경 이미지

v0.11.52는 게임 그래픽을 변경하지 않은 패키징·분석 도구 수정 릴리즈입니다. 직전
v0.11.51에서 확정한 EX 인용문 PNG를 회귀 확인용으로 함께 표시합니다.

### EX 오프닝 인용문

![EX 오프닝 인용문 — v0.11.51 기준](https://raw.githubusercontent.com/snake7594/srwcb-korean-patch/v0.11.51/docs/assets/v0.11.51/ex-opening-quote.png)

### EX 보조 인용문

![EX 보조 인용문 — v0.11.51 기준](https://raw.githubusercontent.com/snake7594/srwcb-korean-patch/v0.11.51/docs/assets/v0.11.51/ex-supplement-quote.png)

## 검증

- `python tools/graphics/savestate_vram.py 23화세이브/SLPS-02070_resume.sav <출력폴더>`
  — zstd/GPU-VRAM 추출 및 PNG 생성 통과
- `python build_all.py --only 7 --version v0.11.52` — 최종 이미지 조립 통과
- `python build_all.py --only 8 --version v0.11.52` — 글리프·레코드·포인터·폭 감사 통과
- 최종 이미지: 566,949,600바이트
- SHA-256: `766be6fcc829306fa56fe5380abee1a95a6a16ca3c613cc996d825432b651ece`
- RetroArch: Track 2 포함 CUE의 BIOS 부팅 통과

## 이슈 상태

- #38: Track 2 필수 검증을 반영했으며 사용자 재시험 대기 — **열어 둠**
- #20: 동적 라인 자산의 관련 세이브스테이트 대기 — **열어 둠**

이번 릴리즈에서는 완전히 재현·확인된 해결 이슈가 없어 이슈를 자동으로 닫지
않았습니다.

릴리즈: https://github.com/snake7594/srwcb-korean-patch/releases/tag/v0.11.52
