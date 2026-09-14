# v0.11.51 — EX 인용문 가독성 재수정

## 변경 내용

v0.11.50에서도 문장은 온전히 들어갔지만, 일반 PC용 글꼴을 16픽셀 TIM으로 축소하면서
획이 굵어지고 자간이 붙어 실제 게임 화면에서 읽기 어려웠습니다. 이번 버전은 저장소의
게임 본문 글꼴과 같은 `Galmuri14` BDF 픽셀 글꼴을 직접 1bpp 셀로 복원해 인용문을
조합합니다.

- EX 오프닝 인용문(C_SMAP member 40, 원본 `0x180412`):
  `고도로 발달한 과학기술은 마술과 구분할 수 없다. 아서 C. 클라크`
- EX 보조 인용문(C_SMAP member 45):
  `자유롭다는 것은, 자유롭도록 저주받은....`
- 한글은 9픽셀 잉크·10픽셀 전진 폭으로 배치하고, 영문·구두점은 글리프별 폭을 적용해
  획과 자간을 분리했습니다.
- 원본의 장식 테두리를 글자 영역으로 오인하지 않도록 밝은 본체 픽셀만 세로 기준으로
  사용했습니다.
- TIM 헤더·CLUT·프레임 폭/높이·타자기 표시 단계·C_SMAP 멤버 배치는 유지했습니다.

## 변경 이미지

아래 이미지는 v0.11.51 최종 C_SMAP의 TIM 프레임을 8배 확대한 미리보기입니다.

### EX 오프닝 인용문

![EX 오프닝 인용문 — v0.11.51](https://raw.githubusercontent.com/snake759494/srwcb-korean-patch/v0.11.51/docs/assets/v0.11.51/ex-opening-quote.png)

### EX 보조 인용문

![EX 보조 인용문 — v0.11.51](https://raw.githubusercontent.com/snake759494/srwcb-korean-patch/v0.11.51/docs/assets/v0.11.51/ex-supplement-quote.png)

## 검증

- `python build_all.py --only 7 --version v0.11.51` — 최종 이미지 조립 및 TIM 왕복 검증 통과
- `python build_all.py --only 8 --version v0.11.51` — 글리프·레코드·포인터·오버플로 감사 통과
- 미번역 레코드 0건, 폭/줄 오버플로 0건, 깨진 레코드 0건, 이벤트 포인터 잔류 0건

릴리즈: https://github.com/snake759494/srwcb-korean-patch/releases/tag/v0.11.51

참고로 GitHub 이슈 [#20](https://github.com/snake759494/srwcb-korean-patch/issues/20)의 동적 한 줄은
정적 C_SMAP 자산이 아니므로 이번 릴리즈의 해결 범위에 포함하지 않았습니다.
