"""
knowledge.py
--------------------------------------------------------
학교 학칙 Markdown(.md) 문서를 읽어, 사용자의 질문과 가장
관련성이 높은 문장을 찾아 Context(문맥)로 반환하는 모듈입니다.

이 모듈은 아래 조건을 지킵니다.
- FAISS, ChromaDB, Embedding, Vector DB를 사용하지 않습니다.
- 초보자가 이해하기 쉬운 "키워드 겹침 개수" 기반의
  단순 문자열 매칭 방식으로 문장 간 유사도를 계산합니다.
- Markdown 문법 기호(#, *, -, [ ]( ) 등)는 제거하고
  순수 텍스트만 남긴 뒤 문장 분리/키워드 매칭을 수행합니다.

--------------------------------------------------------
[버그 수정 메모] "검색 결과가 항상 문서 앞부분(제1조~제N조)이 나온다"
--------------------------------------------------------
원인을 5단계(문장 분리 → 키워드 추출 → 유사도 계산 → 정렬 → top_n 선택)
로 나눠서 코드 흐름을 그대로 따라가며 분석한 결과, 실제 원인은
아래 두 가지가 겹쳐서 발생한 문제였습니다.

[원인 1] top_n 선택 단계에서 "0점 문장 걸러내기"가 무너지면
    문서 순서 그대로 반환된다 (핵심 원인)

  이전 코드는 아래와 같은 흐름이었습니다.

      scored_sentences.sort(...)                       # 점수 내림차순 정렬
      top_sentences = [s for s, sc in scored_sentences[:top_n] if sc > 0]

  만약 질문 키워드("크록스" 등)가 문서 어디에도 전혀 등장하지 않으면
  *모든* 문장의 점수가 0점이 됩니다. Python의 sort()는 "안정 정렬
  (stable sort)"이라서, 점수가 전부 동점(0점)이면 정렬 후에도
  원래 순서(=문서에 쓰여진 순서, 즉 제1조 → 제2조 → 제3조 ...)가
  그대로 유지됩니다.

  이 상태에서 `if sc > 0` 필터링이 어떤 이유로든 빠지거나
  (예: 리팩터링 중 실수로 삭제, 조건 위치 변경 등) 제대로 동작하지
  않으면, top_n개(기본 3개)를 그냥 앞에서부터 잘라가게 되므로
  "제1조, 제2조, 제3조"처럼 항상 문서 맨 앞부분이 선택되는
  현상이 그대로 재현됩니다. (직접 재현 테스트로 확인함)

  → 수정: 정렬하기 *전에* 전체 문장 중 최고 점수(best_score)가
    0인지 먼저 확인해서, 관련 문장이 전혀 없으면 정렬/선택 단계로
    가지 않고 즉시 빈 문자열을 반환하도록 이중 안전장치를 추가했다.
    (get_context 함수의 "best_score == 0" 체크 부분 참고)

[원인 2] "크록스"처럼 문서에 없는 단어는 동의어 확장이 없으면
    애초에 매칭될 수가 없다

  "크록스"라는 단어 자체가 school_rules.md 어디에도 존재하지 않으므로,
  동의어(슬리퍼, 운동화)로 연결해주는 코드가 없으면 calculate_similarity()가
  항상 0을 반환하는 것이 당연한 결과입니다. 이 모듈에는 원래 동의어
  기능이 없었기 때문에, 항상 원인 1(0점 → 문서 순서 반환)로 이어졌습니다.

  → 수정: SYNONYM_MAP과 expand_with_synonyms() 함수를 추가하고,
    get_context()에서 "질문 키워드를 추출한 직후" 반드시 동의어로
    확장한 뒤 유사도를 계산하도록 했다. (사전은 파일 위쪽에 있어
    필요할 때 자유롭게 항목을 추가할 수 있다)

[참고: calculate_similarity의 매칭 방식도 더 안전하게 바꿈]

  이전에는 "질문 키워드 문자열이 문장 안에 포함되어 있는지"를
  단순 부분 문자열(substring)로 검사했다 (`if keyword in sentence`).
  이 방식은 키워드가 2글자처럼 짧을 경우, 전혀 관계없는 긴 문장 안에
  우연히 그 글자가 들어있기만 해도 매칭되는 것으로 착각할 위험이 있다.
  (예: 조사 제거 과정에서 만들어진 "신어"라는 조각이, 관계없는 다른
  단어 속에 우연히 포함되어 있으면 오탐이 발생할 수 있음)

  이를 막기 위해 이제는 "문장에서도 동일한 방식으로 키워드를 추출한 뒤,
  두 키워드 집합(set)이 정확히 겹치는지"를 확인하는 방식으로 바꿨다.
  (calculate_similarity 함수 참고) 이렇게 하면 짧은 키워드 조각이
  엉뚱한 단어 속에 우연히 끼어 들어가 있어도 매칭되지 않는다.
--------------------------------------------------------
[버그 수정 메모 2] "슬리퍼만 단독으로 물어보면 여전히 제1조가 나온다"
--------------------------------------------------------
원인: "겹치는 키워드 개수"를 그대로 점수로 쓰다 보니, "슬리퍼"처럼
학칙 전체에서 드물게 등장하는 단어 1개와 "학교"/"학생"처럼 학칙
문장 227개 중 수십~수백 개에 등장하는 단어 1개가 똑같이 1점으로
취급되었다. "크록스" 질문은 동의어 확장(슬리퍼+운동화)으로 2점을
받아 우연히 동점을 뚫었지만, "슬리퍼"만 물으면 다시 1점으로
"학교"가 우연히 들어간 다른 문장들과 동점이 되고, 정렬이 안정
정렬이라 문서 순서상 앞선 문장(제1조 등)이 먼저 뽑혔다.

수정: 키워드 하나의 점수를 고정 1점이 아니라, 그 키워드가 전체
문서에서 등장하는 문장 수(문서 빈도, document frequency)에 반비례하게
주도록 바꿨다 (희귀한 키워드일수록 더 결정적이라고 보는 것, 흔히
말하는 IDF와 같은 아이디어이지만 임베딩 없이 카운팅만으로 구현한다).
"슬리퍼"처럼 몇 문장에만 등장하는 단어는 높은 가중치를,
"학생"처럼 수십 문장에 등장하는 단어는 낮은 가중치를 받는다.
(_build_keyword_document_frequency, calculate_similarity 함수 참고)
--------------------------------------------------------
"""

import os
import re

# Markdown 파일 경로: project 폴더를 기준으로 data/school_rules.md 를 찾는다.
# (VS Code 등 어떤 위치에서 실행하더라도 항상 이 파일 기준 상대경로를 쓰도록
#  os.path.dirname(__file__)을 사용한다.)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MD_PATH = os.path.join(BASE_DIR, "data", "school_rules.md")

# 질문/문장에서 의미가 거의 없는 단어(불용어)는 미리 제거해
# 키워드 매칭의 정확도를 높인다. 필요에 따라 자유롭게 추가/삭제 가능.
STOPWORDS = {
    "무엇", "어떻게", "그리고", "그러나", "궁금합니다", "알려주세요",
    "것", "수", "있나요", "합니다", "해요",
}

# 한국어는 명사 뒤에 조사(은/는/이/가 등)나 동사 어미(하나요/합니까 등)가
# 붙기 때문에, 단순히 공백으로 단어를 나누면 같은 단어라도 "휴학"과
# "휴학은"처럼 서로 다른 문자열로 인식되어 매칭이 실패한다.
# 형태소 분석기를 쓰지 않는 대신, 아주 단순하게 "자주 쓰이는 접미사 목록"을
# 만들어 두고, 단어 끝부분이 이 목록과 일치하면 잘라내는 방식으로
# 어느 정도 보정한다. (완벽한 형태소 분석은 아니지만 데모 목적으로는 충분함)
PARTICLE_SUFFIXES = sorted([
    "하나요", "합니까", "인가요", "입니까", "되나요", "됩니까", "한가요", "나요", "까요",
    "이라면", "라면", "하려면", "려면", "이지만", "지만", "이라고", "라고", "까지", "부터",
    "이며", "며", "이나", "에게서", "한테", "께서", "이란", "란", "이라", "라",
    "으로", "로", "에서", "에게", "이에요", "예요", "이다",
    "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "만", "다",
], key=len, reverse=True)  # 긴 접미사부터 먼저 검사해야 정확히 잘라낼 수 있음

# 사용자가 문서에 쓰인 정식 단어 대신 다른 표현(브랜드명, 줄임말, 속어 등)을
# 쓸 수 있으므로, 질문에서 뽑아낸 키워드를 문서에 실제로 쓰이는 단어로
# "확장"해주기 위한 동의어 사전이다.
#
# 사용법: {"질문에서 쓸 법한 단어": ["문서에 실제로 등장하는 단어1", "단어2", ...]}
# 필요할 때 아래에 자유롭게 항목을 추가하면 된다.
SYNONYM_MAP = {
    "크록스": ["슬리퍼", "운동화"],
    "쪼리": ["슬리퍼"],
    "삼선슬리퍼": ["슬리퍼"],
}

# "그건", "그거"처럼 이전 대화의 주제를 가리키는 지시어 목록.
#
# [대화형 대응 - 지시어 질문 오매칭 문제] 후속 질문에 이런 지시어가 있으면,
# 질문 자체의 키워드("최대", "며칠"처럼 일반적인 단어)만으로 검색했을 때
# 우연히 전혀 다른 주제의 문장과 매칭되어도 "빈 Context"가 아니므로, 기존
# 로직(현재 질문만으로 찾지 못했을 때만 history_questions를 더하는 방식)은
# 이 오매칭을 잡아내지 못한다. (예: "그건 최대 며칠까지 가능해?"가 "휴학"이
# 아니라 전혀 무관한 "학업중단숙려" 조항과 매칭되는 문제를 실제로 확인함)
# 그래서 질문에 지시어가 있으면, 현재 질문 단독 검색 결과가 있더라도
# 먼저 직전 질문 키워드를 더한 결합 검색을 우선 시도한다.
REFERENTIAL_MARKERS = [
    "그건", "그거", "그것", "그게", "저건", "저거", "저것",
    "이건", "이거", "이것", "그럼", "그러면", "거기", "그때",
]


def _is_referential_question(question: str) -> bool:
    """
    질문이 "그건", "그거"처럼 이전 대화의 주제를 가리키는 지시어를
    포함하는지 확인한다.

    Parameters:
        question (str): 사용자가 입력한 질문

    Returns:
        bool: 지시어가 하나라도 포함되어 있으면 True
    """
    return any(marker in question for marker in REFERENTIAL_MARKERS)

# Markdown 파일을 매 질문마다 다시 읽고 문장을 다시 나누면 느려지기 때문에,
# 최초 1회만 로드해서 이 변수에 캐싱해 둔다.
_sentence_cache = None

# 키워드별 "문서 빈도"(그 키워드가 등장하는 문장 수) 캐시.
# "학교", "학생"처럼 학칙 전체에 흔한 단어의 가중치를 낮추기 위해 사용한다.
_keyword_df_cache = None


def extract_text_from_markdown(md_path: str = MD_PATH) -> str:
    """
    Markdown(.md) 파일을 읽어 원본 텍스트(마크다운 문법 포함)를 반환한다.

    Parameters:
        md_path (str): 읽을 Markdown 파일 경로 (기본값: data/school_rules.md)

    Returns:
        str: 파일 전체 내용을 담은 문자열.
             파일이 없거나 읽기에 실패하면 빈 문자열("")을 반환한다.
    """
    if not os.path.exists(md_path):
        print(f"[knowledge.py] Markdown 파일을 찾을 수 없습니다: {md_path}")
        return ""

    try:
        with open(md_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"[knowledge.py] Markdown 파일 읽기 중 오류가 발생했습니다: {e}")
        return ""


def strip_markdown(text: str) -> str:
    """
    텍스트에서 Markdown 문법 기호만 제거하고 순수 텍스트(plain text)만 남긴다.

    형태소 분석기 없이 정규식으로 아래 항목들을 순서대로 처리한다.
    1. 코드 블록(```...```)은 통째로 제거한다.
    2. 인라인 코드(`code`)는 백틱만 제거하고 안의 글자는 남긴다.
    3. 이미지(![alt](url))는 통째로 제거한다.
    4. 링크([text](url))는 대괄호/URL을 없애고 글자(text)만 남긴다.
    5. 줄 맨 앞의 헤더 기호(#, ##, ### ...)를 제거한다.
    6. 줄 맨 앞의 인용구 기호(>)를 제거한다.
    7. 줄 맨 앞의 목록 기호(-, *, +, 1. 등)를 제거한다.
    8. 굵게(**text**)/기울임(*text*) 등에 쓰이는 *, _ 기호를 제거한다.
    9. 구분선(---, ***, ___)으로만 이루어진 줄을 제거한다.

    Parameters:
        text (str): Markdown 문법이 포함된 원본 텍스트

    Returns:
        str: Markdown 기호가 제거된 순수 텍스트
    """
    if not text:
        return ""

    # 1) 코드 블록 전체 제거 (```로 감싸진 여러 줄)
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)

    # 2) 인라인 코드: 백틱만 제거하고 내용은 유지
    text = re.sub(r"`([^`]*)`", r"\1", text)

    # 3) 이미지 문법(![대체텍스트](경로))은 통째로 제거
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)

    # 4) 링크 문법([보여줄 글자](주소))은 글자만 남기고 나머지는 제거
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)

    # 5) 줄 시작의 헤더 기호(#, ##, ### ...) 제거
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)

    # 6) 줄 시작의 인용구 기호(>) 제거
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.MULTILINE)

    # 7) 줄 시작의 목록 기호(-, *, +) 및 번호 목록(1. 2. ...) 제거
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

    # 8) 굵게/기울임에 쓰이는 *, _ 기호 제거 (남은 글자는 그대로 둔다)
    text = re.sub(r"(\*\*\*|\*\*|\*|___|__|_)", "", text)

    # 9) 구분선(---, ***, ___ 등)으로만 이루어진 줄 제거
    text = re.sub(r"^\s*([-*_])\1{2,}\s*$", "", text, flags=re.MULTILINE)

    return text


def split_into_sentences(text: str) -> list:
    """
    긴 텍스트를 문장 단위로 분리한다. [1단계: 문장 분리]

    한국어 문장은 보통 '.', '!', '?' 로 끝나므로, 이 문자들 뒤의
    공백을 기준으로 정규식을 이용해 나눈다. (형태소 분석기 사용 안 함)

    Parameters:
        text (str): 전체 원문 텍스트

    Returns:
        list[str]: 분리된 문장 리스트 (공백 제거, 너무 짧은 문장은 제외)
    """
    if not text:
        return []

    # 문서에서 추출한 텍스트는 줄바꿈이 문장 중간에 끼어 있는 경우가 많으므로
    # 먼저 줄바꿈을 공백으로 치환해 하나의 긴 문자열로 만든다.
    normalized = text.replace("\n", " ")

    # 마침표/느낌표/물음표 뒤에 오는 공백을 기준으로 문장을 나눈다.
    raw_sentences = re.split(r"(?<=[.!?])\s+", normalized)

    # 앞뒤 공백 제거 후, 의미 없는 너무 짧은 문장(제목 파편 등)은 제외한다.
    # 참고: "...한다. (제19조)"처럼 마침표 뒤에 조항 번호만 남는 경우,
    # 짧은 문장 조각이 하나 더 생길 수 있지만 키워드가 거의 없어
    # 검색 결과에 영향을 주지는 않는다.
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 5]
    return sentences


def _strip_particle(word: str) -> str:
    """
    단어 끝에 붙은 한국어 조사/어미를 간단한 규칙으로 제거한다.

    예) "휴학은" -> "휴학", "슬리퍼는" -> "슬리퍼"

    Parameters:
        word (str): 조사/어미가 붙어 있을 수 있는 단어

    Returns:
        str: 접미사를 제거한 단어. 일치하는 접미사가 없으면 원래 단어 그대로 반환.
    """
    for suffix in PARTICLE_SUFFIXES:
        # 접미사를 제거하고 남는 부분이 최소 1글자는 되어야 한다.
        # (예: "되나요"에서 "나요"를 떼면 "되"만 남는데, 이런 의미 없는
        #  1글자 조각은 아래 extract_keywords()의 길이 필터에서 자동으로
        #  걸러지므로 여기서는 완전히 사라지는 것만 막아주면 된다)
        if word.endswith(suffix) and len(word) - len(suffix) >= 1:
            return word[: -len(suffix)]
    return word


def extract_keywords(text: str) -> set:
    """
    문장(또는 질문)에서 비교에 사용할 '키워드' 집합을 추출한다. [2단계: 키워드 추출]

    질문과 문서의 문장 양쪽 모두 이 함수 하나로 키워드를 뽑기 때문에,
    같은 규칙으로 정규화되어 서로 비교하기 쉬워진다.

    동작 순서:
    1. 한글/영문/숫자만 남기고 특수문자는 공백으로 치환한다.
    2. 공백 기준으로 단어를 나눈다.
    3. 각 단어에서 조사/어미를 제거한다 (_strip_particle).
    4. 한 글자짜리 단어와 불용어(STOPWORDS)는 제외한다.

    Parameters:
        text (str): 키워드를 뽑아낼 문장 또는 질문

    Returns:
        set[str]: 중복이 제거된 키워드 집합
    """
    cleaned = re.sub(r"[^가-힣a-zA-Z0-9\s]", " ", text)
    words = cleaned.split()

    keywords = set()
    for word in words:
        stripped = _strip_particle(word)
        if len(stripped) > 1 and stripped not in STOPWORDS:
            keywords.add(stripped)
    return keywords


def expand_with_synonyms(keywords: set) -> set:
    """
    질문에서 뽑아낸 키워드 집합을, SYNONYM_MAP에 등록된 동의어로 확장한다.

    예) {"크록스"} -> {"크록스", "슬리퍼", "운동화"}

    문서에는 "크록스"라는 단어가 없더라도, 문서에 실제로 쓰인 단어인
    "슬리퍼"/"운동화"가 함께 키워드 집합에 들어가므로 유사도 계산에서
    관련 문장을 찾아낼 수 있게 된다.

    주의: 이 함수는 반드시 "질문 키워드"에만 적용해야 한다. 문장(Context
    후보)의 키워드에도 적용하면 동의어끼리 서로 매칭되어 버려 관련
    없는 문장까지 걸릴 수 있으므로, get_context()에서 질문 키워드를
    추출한 직후에만 호출한다.

    Parameters:
        keywords (set[str]): 원본 키워드 집합 (질문에서 추출한 것)

    Returns:
        set[str]: 동의어가 추가된 키워드 집합
    """
    expanded = set(keywords)
    for keyword in keywords:
        if keyword in SYNONYM_MAP:
            expanded.update(SYNONYM_MAP[keyword])
    return expanded


def get_synonym_note(question: str) -> str:
    """
    질문에 SYNONYM_MAP에 등록된 단어가 있으면, "질문 단어와 문서 단어가
    같은 의미"라고 LLM에게 알려주는 안내 문장을 만든다.

    [버그 수정] expand_with_synonyms()는 검색(Context 찾기) 단계에서만
    쓰이고, 그 결과 찾아낸 Context 문장에는 "크록스"라는 단어 자체가
    등장하지 않는다. 그래서 llm.generate_answer()가 질문("크록스")과
    Context("슬리퍼")만 보면, 시스템 프롬프트의 "Context에 없는 사실을
    지어내지 않는다" 규칙 때문에 "크록스"가 언급된 조항이 없다고 판단해
    자신 없는 답변을 하게 된다 (Confidence Score도 함께 낮아짐).
    이를 막기 위해 "질문 단어 = 문서 단어" 관계를 별도 안내 문장으로
    만들어 llm.generate_answer()에 함께 전달한다.

    Parameters:
        question (str): 사용자가 입력한 질문

    Returns:
        str: "'크록스'는 '슬리퍼'/'운동화'와 같은 의미로 취급합니다." 같은
             안내 문장들을 이어붙인 문자열. 등록된 동의어가 없으면 빈 문자열.
    """
    keywords = extract_keywords(question)
    notes = []
    for keyword in sorted(keywords):
        if keyword in SYNONYM_MAP:
            doc_words = "/".join(f"'{word}'" for word in SYNONYM_MAP[keyword])
            notes.append(f"'{keyword}'는 {doc_words}와(과) 같은 의미로 취급합니다.")
    return " ".join(notes)


def _build_keyword_document_frequency(sentences: list) -> dict:
    """
    각 키워드가 전체 문장 중 몇 개의 문장에 등장하는지("문서 빈도")를 센다.

    "학교", "학생"처럼 학칙 문서 전체에 흔하게 등장하는 단어는 문서 빈도가
    크고, "슬리퍼"처럼 몇 문장에만 등장하는 단어는 문서 빈도가 작다.
    calculate_similarity()에서 이 값의 역수를 가중치로 사용해, 흔한
    단어일수록 매칭 점수에 기여하는 비중을 낮춘다.

    Parameters:
        sentences (list[str]): 전체 문장 리스트

    Returns:
        dict[str, int]: {키워드: 그 키워드가 등장하는 문장 수}
    """
    df = {}
    for sentence in sentences:
        for keyword in extract_keywords(sentence):
            df[keyword] = df.get(keyword, 0) + 1
    return df


def _load_keyword_df() -> dict:
    """
    문서 빈도(document frequency) 계산 결과를 캐싱해서 반환하는 내부 함수.
    (_load_sentences와 동일한 이유로 캐싱한다: 매 질문마다 다시 계산하면 느리다)
    """
    global _keyword_df_cache
    if _keyword_df_cache is None:
        _keyword_df_cache = _build_keyword_document_frequency(_load_sentences())
    return _keyword_df_cache


def calculate_similarity(question_keywords: set, sentence: str, keyword_df: dict) -> float:
    """
    질문 키워드와 한 문장이 얼마나 관련 있는지를 계산한다. [3단계: 유사도 계산]

    임베딩 기반 유사도가 아니라, "문장에서도 동일한 방식으로 키워드를
    추출한 뒤, 두 키워드 집합이 정확히 겹치는지"를 확인하는 방식이다.

    (이전 버전은 `keyword in sentence`처럼 단순 부분 문자열 포함 여부로
    계산했는데, 이 방식은 짧은 키워드 조각이 전혀 관계없는 단어 속에
    우연히 포함되어 있어도 매칭된 것으로 잘못 인식하는 문제가 있었다.
    두 문장 모두 같은 규칙으로 "단어 단위" 키워드를 뽑아 집합으로
    비교하면 이런 오탐을 막을 수 있다)

    [버그 수정 메모 2 반영] 겹치는 키워드 개수를 그대로 더하면 "학교"처럼
    문서 전체에 흔한 단어와 "슬리퍼"처럼 드문 단어가 똑같이 1점씩 취급되어,
    실제로 관련 없는 문장이 진짜 관련 문장과 동점이 되는 문제가 있었다.
    이를 막기 위해 매칭된 키워드마다 1점이 아니라 "1 / 그 키워드의 문서 빈도"
    만큼만 더한다. 흔한 단어는 기여도가 작아지고, 드문 단어는 기여도가
    커진다.

    Parameters:
        question_keywords (set[str]): 질문에서 추출(+동의어 확장)한 키워드 집합
        sentence (str): 비교 대상 문장
        keyword_df (dict[str, int]): 키워드별 문서 빈도 (_load_keyword_df 참고)

    Returns:
        float: 겹치는 키워드들의 가중치 합 (클수록 관련성이 높음)
    """
    sentence_keywords = extract_keywords(sentence)
    matched_keywords = question_keywords & sentence_keywords
    return sum(1.0 / keyword_df.get(keyword, 1) for keyword in matched_keywords)


def _load_sentences() -> list:
    """
    Markdown 파일을 읽고, 마크다운 문법을 제거한 뒤, 문장 단위로
    분리한 결과를 캐싱해서 반환하는 내부 함수.

    Streamlit은 사용자가 상호작용할 때마다 스크립트를 다시 실행하므로,
    매번 파일을 새로 읽고 파싱하면 속도가 느려진다. 이를 방지하기 위해
    모듈 전역 변수(_sentence_cache)에 한 번만 로드해 재사용한다.

    Returns:
        list[str]: 캐싱된 문장 리스트
    """
    global _sentence_cache
    if _sentence_cache is None:
        raw_markdown = extract_text_from_markdown()
        plain_text = strip_markdown(raw_markdown)
        _sentence_cache = split_into_sentences(plain_text)
    return _sentence_cache


def _search_with_keywords(keywords: set, sentences: list, keyword_df: dict, top_n: int) -> str:
    """
    주어진 키워드 집합으로 문장들을 검색해 Context 문자열을 만드는 내부 함수.

    get_context()의 3~5단계(유사도 계산 -> 정렬 -> top_n 선택)를 모아둔
    것으로, 현재 질문만으로 검색할 때와 이전 질문 키워드를 더해 다시
    검색할 때(후속 질문 대응) 양쪽에서 재사용한다.

    Parameters:
        keywords (set[str]): 검색에 사용할 키워드 집합 (이미 동의어 확장된 상태)
        sentences (list[str]): 검색 대상 문장 리스트
        keyword_df (dict[str, int]): 키워드별 문서 빈도
        top_n (int): Context에 포함할 최대 문장 수

    Returns:
        str: 관련 문장들을 줄바꿈으로 이어붙인 Context 문자열.
             관련 문장을 찾지 못하면 빈 문자열("")을 반환한다.
    """
    scored_sentences = [
        (sentence, calculate_similarity(keywords, sentence, keyword_df))
        for sentence in sentences
    ]

    # [핵심 버그 수정] 모든 문장의 점수가 0이라면 여기서 즉시 빈 문자열을
    # 반환해야 한다. 그렇지 않으면 아래 sort()가 동점을 문서 순서 그대로
    # 유지하기 때문에, 관련 없는 질문에도 항상 문서 맨 앞부분(제1조,
    # 제2조...)이 선택되는 문제가 생긴다.
    best_score = max(score for _, score in scored_sentences)
    if best_score == 0:
        return ""

    scored_sentences.sort(key=lambda pair: pair[1], reverse=True)

    # 상위 top_n개 중에서도 "0점 문장"과 "1등과 비교해 너무 점수 차이가
    # 크게 나는 문장"을 걸러낸다. 1등 점수 대비 일정 비율(MIN_SCORE_RATIO)
    # 미만이면 사실상 무관한 문장으로 보고 제외한다.
    MIN_SCORE_RATIO = 0.3
    score_threshold = best_score * MIN_SCORE_RATIO
    top_sentences = [
        s for s, sim_score in scored_sentences[:top_n]
        if sim_score > 0 and sim_score >= score_threshold
    ]

    return "\n".join(top_sentences)


def get_context(question: str, top_n: int = 3, history_questions: list = None) -> str:
    """
    사용자의 질문과 가장 관련성이 높은 문장(들)을 찾아,
    LLM에 전달할 Context 문자열로 반환하는 메인 함수.

    동작 순서 (요청하신 5단계와 1:1로 대응):
    1. [문장 분리] Markdown 문서에서 마크다운 기호를 제거하고 추출한
       문장 리스트를 불러온다 (캐시 사용, _load_sentences -> split_into_sentences).
    2. [키워드 추출] 질문에서 키워드를 추출하고(extract_keywords),
       동의어 사전으로 키워드를 확장한다(expand_with_synonyms).
    3. [유사도 계산] 모든 문장에 대해 키워드 겹침 점수를 계산한다
       (calculate_similarity).
    4. [정렬] 점수가 높은 순으로 정렬한다. 단, 정렬하기 전에 "가장 높은
       점수가 0인지"부터 확인해서, 관련 문장이 전혀 없으면 정렬/선택
       단계로 가지 않고 즉시 빈 문자열을 반환한다.
    5. [top_n 선택] 정렬된 목록에서 점수가 0보다 크면서, 1등 점수 대비
       너무 낮지 않은(MIN_SCORE_RATIO 이상인) 문장만 최대 top_n개까지
       골라 하나의 문자열로 합쳐서 반환한다.

    [대화형 대응] "그건 며칠이야?"처럼 질문 자체에 키워드가 거의 없거나
    문서와 매칭되지 않는 후속 질문은, 위 단계만으로는 항상 빈 Context를
    반환하게 된다. 이를 보완하기 위해 history_questions(직전 질문들)가
    주어지면 직전 질문의 키워드를 더해 검색을 시도한다.

    [지시어 질문 오매칭 문제] 다만 "그건 최대 며칠까지 가능해?"처럼 질문에
    "최대", "며칠"같은 흔하지 않은 단어가 있으면, 그 단어만으로도 우연히
    (원래 주제와 무관한) 다른 문장과 매칭되어 버려서 "빈 Context"가 아니게
    될 수 있다. 이 경우 기존 방식(현재 질문만으로 못 찾았을 때만 history를
    더하는 방식)은 오매칭을 잡아내지 못한다. 그래서 질문에 "그건", "그거"
    같은 지시어(REFERENTIAL_MARKERS)가 있으면, 현재 질문 단독 검색이
    성공하더라도 직전 질문 키워드를 더한 결합 검색을 먼저 시도한다.

    Parameters:
        question (str): 사용자가 입력한 질문
        top_n (int): Context에 포함할 최대 문장 수 (기본값 3)
        history_questions (list[str] | None): 대화 맥락 보완용 직전 질문들
            (오래된 것 -> 최근 순서 상관없음, 키워드 합집합만 사용한다)

    Returns:
        str: 관련 문장들을 줄바꿈으로 이어붙인 Context 문자열.
             관련 문장을 찾지 못하면 빈 문자열("")을 반환한다.
    """
    # 1) 문장 분리 (캐시된 결과 사용)
    sentences = _load_sentences()
    if not sentences:
        return ""

    keyword_df = _load_keyword_df()

    # 2) 키워드 추출 + 동의어 확장
    question_keywords = expand_with_synonyms(extract_keywords(question))

    combined_keywords = set(question_keywords)
    if history_questions:
        for prev_question in history_questions:
            combined_keywords |= expand_with_synonyms(extract_keywords(prev_question))
    has_history_boost = combined_keywords != question_keywords

    # 지시어가 있는 후속 질문은, 질문 단독 검색이 우연히 무관한 문장과
    # 매칭될 위험이 있으므로 결합 검색을 먼저 시도한다.
    if has_history_boost and _is_referential_question(question):
        context = _search_with_keywords(combined_keywords, sentences, keyword_df, top_n)
        if context:
            return context

    # 기본 순서: 현재 질문만으로 먼저 검색한다.
    if question_keywords:
        context = _search_with_keywords(question_keywords, sentences, keyword_df, top_n)
        if context:
            return context

    # 현재 질문만으로는 관련 문장을 찾지 못한 경우, 직전 질문들의 키워드를
    # 더해 다시 검색해본다 (후속 질문 대응).
    if has_history_boost:
        return _search_with_keywords(combined_keywords, sentences, keyword_df, top_n)

    return ""


# 이 파일을 직접 실행하면(python knowledge.py) 간단히 동작을 테스트할 수 있다.
if __name__ == "__main__":
    test_questions = [
        "휴학은 어떻게 신청하나요?",
        "크록스 신어도 되나요?",       # 문서에 없는 단어 -> 동의어 확장 테스트
        "복사기는 어디에 있나요?",      # 문서와 관련 없는 질문 -> 빈 Context가 나와야 정상
    ]
    for q in test_questions:
        print(f"질문: {q}")
        ctx = get_context(q)
        print("찾은 Context:")
        print(ctx if ctx else "(관련 문장을 찾지 못했습니다 - 빈 문자열)")
        print("-" * 40)
