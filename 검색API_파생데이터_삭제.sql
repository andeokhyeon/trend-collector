-- ============================================================
--  검색 API 파생 데이터 삭제  (2026-09-23)
-- ============================================================
--  왜: 네이버 개발자센터 회신(2026-09-22) 4번 —
--      "검색결과를 분석하여 생성한 집계 수치는 (2.4 임시보관) 대상으로 보기 어려우며,
--       2.3에서 제한하는 가공·파생물에 해당할 수 있다."
--      → 문서수·최근 새 글·경쟁률·순위 같은 값은 '줄여서 보관'이 아니라 '보관 불가'.
--
--  무엇을:
--    1) trends_master   : 문서수·최근 새 글·경쟁률·기회 점수 열 비우기, 뉴스(크롤링) 행 삭제
--    2) tracking_history: 순위·문서수·최근 새 글·경쟁률·기회 점수 열 비우기
--    3) keyword_pool    : 문서수·문서수 잰 시각 비우기
--    4) api_cache       : 블로그 검색·상위글·자동완성 응답 캐시 삭제
--
--  ⚠️ 남기는 것: 월 검색량·PC/모바일·광고 경쟁(검색광고 API),
--     주간 캘린더(weekly_event) 행의 comp_ratio·comp_grade — comp_ratio는 '작년 급등이
--     며칠 앞섰나'(검색어트렌드 값)라 열 이름만 같을 뿐 블로그 검색과 무관하다.
--     그래서 weekly_event 행은 이 두 열을 건드리지 않는다.
--
--  사용법: Supabase → SQL Editor → 이 파일 전체를 붙여넣고 Run.
--         없는 열·없는 표가 있어도 멈추지 않고 건너뛴다. 여러 번 돌려도 안전하다.
-- ============================================================

DO $$
DECLARE
  -- (표, 열, weekly_event 행은 건너뛸지)
  targets text[][] := ARRAY[
    ['trends_master',    'blog_total_docs',  'n'],
    ['trends_master',    'blog_competition', 'n'],
    ['trends_master',    'recent_docs',      'n'],
    ['trends_master',    'comp_ratio',       'y'],
    ['trends_master',    'comp_grade',       'y'],
    ['trends_master',    'opportunity',      'n'],
    ['tracking_history', 'my_rank',          'n'],
    ['tracking_history', 'blog_total_docs',  'n'],
    ['tracking_history', 'recent_docs',      'n'],
    ['tracking_history', 'comp_ratio',       'n'],
    ['tracking_history', 'opportunity',      'n'],
    ['keyword_pool',     'blog_total_docs',  'n'],
    ['keyword_pool',     'docs_checked_at',  'n']
  ];
  t text[];
  n bigint;
BEGIN
  FOREACH t SLICE 1 IN ARRAY targets LOOP
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = t[1] AND column_name = t[2]) THEN
      -- NOT NULL이 걸려 있으면 비울 수 없으니 먼저 푼다 (수집기가 더는 이 열을 채우지 않는다)
      EXECUTE format('ALTER TABLE public.%I ALTER COLUMN %I DROP NOT NULL', t[1], t[2]);
      IF t[3] = 'y' THEN
        EXECUTE format('UPDATE public.%I SET %I = NULL WHERE %I IS NOT NULL '
                       'AND coalesce(source, '''') <> ''weekly_event''', t[1], t[2], t[2]);
      ELSE
        EXECUTE format('UPDATE public.%I SET %I = NULL WHERE %I IS NOT NULL', t[1], t[2], t[2]);
      END IF;
      GET DIAGNOSTICS n = ROW_COUNT;
      RAISE NOTICE '비움: %.% — %행', t[1], t[2], n;
    ELSE
      RAISE NOTICE '건너뜀(열 없음): %.%', t[1], t[2];
    END IF;
  END LOOP;

  -- 뉴스 탭 행 (news.naver.com 크롤링으로 모은 것)
  IF to_regclass('public.trends_master') IS NOT NULL THEN
    DELETE FROM public.trends_master WHERE source = 'naver_news';
    GET DIAGNOSTICS n = ROW_COUNT;
    RAISE NOTICE '삭제: trends_master 뉴스 행 — %행', n;
  END IF;

  -- 블로그 검색·상위 글·자동완성 응답 캐시
  IF to_regclass('public.api_cache') IS NOT NULL THEN
    DELETE FROM public.api_cache
     WHERE cache_key LIKE 'blogstats|%' OR cache_key LIKE 'docs|%'
        OR cache_key LIKE 'serp|%'      OR cache_key LIKE 'ac|%';
    GET DIAGNOSTICS n = ROW_COUNT;
    RAISE NOTICE '삭제: api_cache 검색 API 응답 — %행', n;
  END IF;
END $$;
