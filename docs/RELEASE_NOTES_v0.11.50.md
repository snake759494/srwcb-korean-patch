# v0.11.50 — EX 인용문 가독성 패치

## 변경 내용

v0.11.49에서 한글 문장 자체는 반영됐지만, 실제 게임의 16픽셀 높이 4bpp TIM 글판에서는
기울임·팽창 처리와 어두운 윤곽색이 한글 획을 뭉개 가독성이 떨어졌습니다. 이번 버전은
GitHub 이슈 [#21](https://github.com/snake759494/srwcb-korean-patch/issues/21)의 두 EX 인용문을
최종 게임 프레임 기준으로 다시 조합했습니다.

- EX 오프닝 인용문(C_SMAP member 40)의 문장을
  `고도로 발달한 과학기술은 마술과 구분할 수 없다. 아서 C. 클라크`로 수정했습니다.
- 보조 인용문(C_SMAP member 45)의 문장을
  `자유롭다는 것은, 자유롭도록 저주받은....`으로 수정했습니다.
- 고해상도 한글 글꼴을 먼저 렌더링한 뒤 4bpp로 양자화하고, 기울임·과도한 팽창을 제거해
  작은 TIM에서도 밝은 글자 획이 유지되도록 했습니다.
- TIM 헤더·CLUT·프레임 폭/높이·문자 표시 단계와 C_SMAP 멤버 오프셋은 유지했습니다.

## 변경 이미지

아래 이미지는 실제 v0.11.50 최종 TIM 프레임을 8배 확대한 미리보기입니다.

### EX 오프닝 인용문

![EX 오프닝 인용문 — v0.11.50](https://raw.githubusercontent.com/snake759494/srwcb-korean-patch/main/docs/assets/v0.11.50/ex-opening-quote.png)

### EX 보조 인용문

![EX 보조 인용문 — v0.11.50](https://raw.githubusercontent.com/snake759494/srwcb-korean-patch/main/docs/assets/v0.11.50/ex-supplement-quote.png)

## 검증

- `python build_all.py --only 7 --version v0.11.50` — 최종 이미지 조립 성공
- `python build_all.py --only 8 --version v0.11.50` — 글리프·레코드·포인터·오버플로 감사 통과
- 번역되지 않은 레코드 0건, 폭/줄 오버플로 0건, 깨진 레코드 0건, 이벤트 포인터 잔류 0건

참고로 GitHub 이슈 [#20](https://github.com/snake759494/srwcb-korean-patch/issues/20)의 동적 한 줄은
정적 C_SMAP 자산이 아니므로 이번 릴리스의 해결 범위에 포함하지 않았습니다.
