# v0.11.47 — 제2차 페이즈 UI 최종 반영

이번 릴리스는 GitHub 이슈 [#34](https://github.com/snake7594/srwcb-korean-patch/issues/34)의
제2차 페이즈 종료 화면을 최종 컴플리트 박스 이미지까지 반영하고, [#35](https://github.com/snake7594/srwcb-korean-patch/issues/35)의
타이틀 메뉴 통일을 포함합니다.

## #34 패치

- 원인은 `image-build/build_image.py`가 최신 `font_extracted/SECOND/SECOND.WAR`가 아니라
  오래된 v0.8.7 중간 이미지에서 제2차 실행파일을 다시 추출하던 경로였습니다.
- 이제 제2차 확장 빌드의 최신 `font_extracted` 파일을 직접 조립 입력으로 사용합니다.
- 최종 `SECOND_SECOND.WAR`의 UI master entry 20 포인터가 가리키는 레코드에서
  `FC 0B FC F8 82`가 1건이고 이전 `FC 10 FC F8 82`가 0건인지 검사하는
  `audit/verify_phase_end_ui.py`를 추가했습니다.

## #35 포함 내용

컴플리트 박스 `C_SMAP.BIN`의 제2차·제3차·EX 타이틀 그래픽 멤버 25·29·33을 모두 패치해
메뉴 9장씩을 `시작`·`로드`·`이어하기`로 통일했습니다. TIM 구조·렌더링 기대값도 자동 검사합니다.

## 검증

- 전체 감사: 미번역 0건, 폭/줄 넘침 0건, 깨진 레코드 0건, 제2차 이벤트 풀 잔류 포인터 0건
- 제2차 페이즈 종료 UI: `FC 0B` 1건, `FC 10` 0건
- 제2차·제3차·EX 타이틀 메뉴: 각 9장, TIM 구조·픽셀 기대값 일치
- 컴플리트 박스 및 제2차·제3차·EX 단독판 xdelta 역적용 검증 통과

배포 파일의 SHA-256은 [`release/SHA256SUMS_v0.11.47.txt`](../release/SHA256SUMS_v0.11.47.txt)에
기록했습니다.
