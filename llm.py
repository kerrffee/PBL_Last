"""
llm.py
--------------------------------------------------------
LLM 호출을 담당하는 모듈입니다.

OpenAI API와 오픈소스 LLM(OpenAI 호환 API, Ollama 등)을
동일한 인터페이스로 사용할 수 있도록 클라이언트를 하나로
통일했습니다. .env 파일의 환경변수만 바꾸면 다른 코드를
수정하지 않고도 백엔드를 교체할 수 있습니다.

사용 예시 (.env 파일):

  [OpenAI 정식 API 사용 시]
  LLM_BASE_URL=https://api.openai.com/v1
  LLM_API_KEY=sk-실제키
  LLM_MODEL=gpt-4o-mini

  [Ollama 사용 시 - Ollama는 OpenAI 호환 엔드포인트를 기본 제공한다]
  LLM_BASE_URL=http://localhost:11434/v1
  LLM_API_KEY=ollama              # 아무 문자열이나 가능 (Ollama는 키를 검사하지 않음)
  LLM_MODEL=llama3

  [LM Studio 등 다른 OpenAI 호환 서버도 동일한 방식으로 사용 가능]

--------------------------------------------------------
[오류 수정 메모] 'ascii' codec can't encode character '\\u2014'
--------------------------------------------------------
학칙 문서(Context)나 시스템 프롬프트 안에 워드프로세서에서 자동 변환된
"타이포그래피" 특수문자, 예를 들어 em dash(—, U+2014), 곡선 따옴표
(" " U+201C/U+201D, ' ' U+2018/U+2019), 말줄임표(…, U+2026) 등이
섞여 있으면, OpenAI 클라이언트(내부적으로 httpx 사용)가 요청을 만드는
과정이나 실행 환경(특히 Windows 콘솔)이 문자열을 ascii로 인코딩하려다
실패하면서 위 오류가 발생할 수 있습니다.

이를 근본적으로 막기 위해 아래 두 가지 안전장치를 추가했습니다.

1. LLM에 전달되는 모든 문자열(시스템 프롬프트, 질문, Context, 환경변수 값)은
   sanitize_text()를 거쳐 문제가 되는 타이포그래피 특수문자를 안전한
   ASCII 문자(-, ", ', ...)로 치환합니다. (한글/영문 등 정상적인 문자는
   그대로 유지되며, 이 특수문자들만 선택적으로 바뀝니다)
2. 치환 후에도 혹시 남아있을 수 있는 깨진 문자를 대비해, UTF-8로
   encode/decode 왕복 처리(errors="ignore")를 한 번 더 거쳐 항상
   올바른 UTF-8 문자열만 API 호출에 사용되도록 보장합니다.
--------------------------------------------------------
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

# .env 파일에 저장된 환경변수를 읽어온다 (없으면 무시하고 기본값 사용)
load_dotenv()

# LLM에 전달하기 전, 문제를 일으키는 "스마트/타이포그래피" 특수문자를
# 안전한 ASCII 문자로 바꾸기 위한 매핑 테이블.
# (워드프로세서에서 자동 변환되는 문자들이 주로 여기에 해당한다)
_TYPOGRAPHIC_CHAR_MAP = {
    "—": "-",   # — em dash (긴 줄표)
    "–": "-",   # – en dash (중간 줄표)
    "‘": "'",   # ' 왼쪽 곡선 작은따옴표
    "’": "'",   # ' 오른쪽 곡선 작은따옴표
    "“": '"',   # " 왼쪽 곡선 큰따옴표
    "”": '"',   # " 오른쪽 곡선 큰따옴표
    "…": "...",  # … 말줄임표
    " ": " ",   # 줄바꿈 없는 공백(non-breaking space)
    "​": "",    # 폭 없는 공백(zero-width space)
    "﻿": "",    # BOM(Byte Order Mark)
}


def sanitize_text(text) -> str:
    """
    LLM에 전달할 문자열에서 문제를 일으킬 수 있는 특수문자를
    안전한 문자로 치환하고, 항상 올바른 UTF-8 문자열만 남긴다.

    시스템 프롬프트, 질문, knowledge.py가 찾아온 Context 등
    외부(문서/사용자 입력)에서 온 모든 텍스트는 이 함수를 거친 뒤에만
    OpenAI API 호출에 사용한다.

    동작 순서:
    1. None이거나 문자열이 아니면 빈 문자열로 취급한다.
    2. em dash(—), 곡선 따옴표(" " ' '), 말줄임표(…) 등
       ASCII 범위를 벗어나는 타이포그래피 문자를 안전한 ASCII 문자로 바꾼다.
    3. UTF-8로 encode 후 다시 decode하여, 혹시 남아있을 수 있는
       깨지거나 잘못된 문자를 제거하고 항상 유효한 UTF-8 문자열만 남긴다.
       (한글, 영문 등 정상적인 UTF-8 문자는 이 과정에서 사라지지 않는다)

    Parameters:
        text: 정제할 원본 값 (보통 str이지만 None이 들어올 수도 있음)

    Returns:
        str: 특수문자가 치환되고 UTF-8로 안전하게 정제된 문자열
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # 1) 문제가 되는 타이포그래피 특수문자를 안전한 ASCII 문자로 치환
    for problem_char, safe_char in _TYPOGRAPHIC_CHAR_MAP.items():
        text = text.replace(problem_char, safe_char)

    # 2) UTF-8 인코딩/디코딩 왕복으로 항상 유효한 UTF-8 문자열만 남긴다.
    #    errors="ignore"는 인코딩 자체가 불가능한(깨진) 바이트만 제거하며,
    #    정상적인 한글/영문/숫자 등은 영향을 받지 않는다.
    text = text.encode("utf-8", errors="ignore").decode("utf-8")

    return text


# 환경변수에서 LLM 접속 정보를 읽고, 혹시 붙어 있을 수 있는 타이포그래피
# 특수문자나 BOM 등을 제거해 항상 안전한 값으로 클라이언트를 생성한다.
# (예: .env 파일을 워드프로세서로 편집하다 실수로 em dash가 섞여 들어간 경우 등)
LLM_BASE_URL = sanitize_text(os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")).strip()
LLM_API_KEY = sanitize_text(os.getenv("LLM_API_KEY", "not-needed")).strip()
LLM_MODEL = sanitize_text(os.getenv("LLM_MODEL", "gpt-4o-mini")).strip()
print("BASE_URL =", repr(LLM_BASE_URL))
print("MODEL =", repr(LLM_MODEL))
print("API KEY PREFIX =", LLM_API_KEY[:12])

# OpenAI 호환 클라이언트를 모듈이 로드될 때 한 번만 생성해서 재사용한다.
# base_url만 바꿔주면 OpenAI든, Ollama든, 다른 OpenAI 호환 서버든 동일한
# client.chat.completions.create(...) 코드로 호출할 수 있다.
client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)


def _chat(messages: list, temperature: float = 0.3) -> str:
    """
    OpenAI 호환 Chat Completion API를 실제로 호출하는 내부(저수준) 함수.

    generate_answer()와 score.py의 evaluate_confidence()가 내부적으로
    호출하는 simple_completion()이 공통으로 이 함수를 사용한다.

    전달되는 messages의 각 content는 호출 전에 이미 sanitize_text()로
    정제되어 있어야 한다 (generate_answer / simple_completion에서 처리).
    이 함수는 최종적으로 client.chat.completions.create(...)를 호출하기
    직전 지점이므로, 여기서도 한 번 더 안전하게 UTF-8 문자열인지 확인한다.

    Parameters:
        messages (list[dict]): [{"role": "system"/"user", "content": "..."}] 형태의 대화 목록
        temperature (float): 답변의 무작위성 정도 (0에 가까울수록 일관된 답변)

    Returns:
        str: LLM이 생성한 답변 텍스트. 호출 중 오류가 나면 오류 메시지 문자열을 반환한다.
    """
    # 혹시 모를 상황을 대비해, API를 호출하기 직전 마지막 안전장치로
    # 모든 메시지의 content를 다시 한번 UTF-8 문자열로 정제한다.
    safe_messages = [
        {"role": m["role"], "content": sanitize_text(m.get("content", ""))}
        for m in messages
    ]

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=safe_messages,
            temperature=temperature,
        )
        answer = response.choices[0].message.content.strip()
        # LLM이 생성한 답변에도 타이포그래피 특수문자가 포함될 수 있으므로
        # 화면 표시/후속 처리 전에 동일하게 정제한다.
        return sanitize_text(answer)
    except UnicodeEncodeError as e:
        # sanitize_text()로도 걸러지지 않은 인코딩 문제가 발생한 경우를 대비한
        # 전용 예외 처리. 오류 메시지 자체도 안전하게 정제해서 반환한다.
        return f"[오류] 문자 인코딩 문제로 LLM 호출에 실패했습니다: {sanitize_text(str(e))}"
    except Exception as e:
        # 예외를 그대로 던지지 않고 문자열로 반환하는 이유는,
        # Streamlit 화면에서 앱이 죽지 않고 오류 내용을 답변란에 보여주기 위함이다.
        return f"[오류] LLM 호출에 실패했습니다: {sanitize_text(str(e))}"


def generate_answer(question: str, context: str = "", history: list = None, synonym_note: str = "") -> str:
    """
    사용자의 질문과, knowledge.py가 찾아온 학칙 Context를 함께
    LLM에 전달하여 답변을 생성한다.

    질문만 전달하지 않고 Context를 함께 전달함으로써, LLM이 학칙
    원문 문장에 근거해 답변하도록 유도한다 (문서 기반 Q&A).

    질문과 Context는 학칙 문서(원본 파일)나 사용자 입력에서 오기 때문에
    em dash, 곡선 따옴표 같은 타이포그래피 특수문자가 섞여 있을 수 있다.
    OpenAI API 호출 전에 sanitize_text()로 정제해 인코딩 오류를 예방한다.

    [대화형 대응] history를 넘기면 직전 몇 턴의 질문/답변을 실제 대화
    메시지(user/assistant)로 함께 전달한다. 이렇게 하면 "그건 며칠이야?"
    처럼 이전 답변을 가리키는 후속 질문도 LLM이 무엇을 묻는지 이해할 수
    있다. 다만 사실적 근거(숫자/기간/조건 등)는 여전히 이번 메시지의
    Context에서만 가져오도록 시스템 프롬프트에 명시한다 - history는
    "무엇을 묻는지" 이해용이지 "무엇이 사실인지"의 근거가 아니다.

    Parameters:
        question (str): 사용자 질문
        context (str): knowledge.get_context()가 찾아온 관련 학칙 문장들.
                        관련 문장을 찾지 못한 경우 빈 문자열일 수 있다.
        history (list[dict] | None): 직전 대화 턴들. 각 항목은
                        {"question": str, "answer": str} 형태이며,
                        오래된 턴 -> 최근 턴 순서로 전달해야 한다.
        synonym_note (str): knowledge.get_synonym_note()가 만든 안내 문장.
                        질문에 "크록스"처럼 Context 문장에는 등장하지 않는
                        동의어가 쓰였을 때, "'크록스'는 '슬리퍼'와 같은
                        의미로 취급합니다."처럼 둘이 같은 뜻임을 LLM에게
                        알려준다. 이게 없으면 LLM은 Context에 그 단어가
                        없다고 보고 "찾을 수 없습니다"로 답하며 Confidence
                        Score도 낮아진다. 등록된 동의어가 없으면 빈 문자열.

    Returns:
        str: LLM이 생성한 답변
    """
       # 질문/Context를 API로 보내기 전에 먼저 안전한 UTF-8 문자열로 정제한다.
    safe_question = sanitize_text(question)
    safe_context = sanitize_text(context)
    safe_synonym_note = sanitize_text(synonym_note)

    system_prompt = """
당신은 학교 학칙 Q&A 챗봇입니다.

이 대화는 여러 턴에 걸쳐 이어질 수 있습니다. 이전 대화 메시지가 함께
주어진다면, 그것은 오직 이번 질문이 "무엇을 가리키는지"(예: "그건",
"거기", "며칠이야?" 같은 지시어/생략된 주어) 이해하는 데만 사용하세요.
답변에 사용하는 사실적 근거(숫자, 기간, 조건, 절차 등)는 이전 대화
내용이 아니라 반드시 이번 메시지의 [학칙 관련 내용](Context)에서만
가져와야 합니다. 이전 답변에 있었던 내용이라도 이번 Context에 없으면
사실로 단정하지 말고, 아래 규칙(특히 4번)에 따라 처리하세요.

답하기 전에 아래 순서로 먼저 판단하세요 (반드시 이 순서대로 확인).
1단계: [학칙 관련 내용](Context) 문장 안에 "~규정에 따른다", "~에서 정한다",
       "~에 의한다"처럼 다른 문서/규정으로 위임하는 표현이 있는가?
       -> 있다면 절대로 "찾을 수 없습니다"라고 쓰지 말고, 곧바로 규칙 3만
          따르세요. (다른 규칙 검토 없이 3번으로 바로 이동)
2단계: 1단계가 아니라면, Context 안에 질문 주제와 관련된 조항이 있는가?
       -> 있다면 규칙 2를 따르세요.
3단계: Context 안에 질문 주제와 관련된 내용이 전혀 없다면 규칙 4를 따르세요.

규칙
1. 반드시 [학칙 관련 내용](Context)에 있는 내용에 근거해서만 답변합니다.
   Context에 없는 사실을 새로 지어내거나, 일반적인 학교 규정을 추측해서
   덧붙이지 않습니다.
2. 다만 Context의 문장을 토씨 하나까지 그대로 담고 있어야만 답할 수 있는
   것은 아닙니다. 질문이 쓴 단어(예: "매일", "항상")가 Context 문장에
   똑같이 없더라도, Context의 내용이 논리적으로 그 질문에 대한 답이
   된다면 Context 문장을 재구성/요약해서 답합니다.
   예) Context: "교내 복장은 학교 지정 교복을 착용한다" (예외 조건 없음)
       질문: "교복을 매일 입어야 하나요?"
       -> "네, 별도 예외가 명시되어 있지 않아 교내에서는 교복을
          착용해야 합니다."처럼 답할 수 있다.
   또한 메시지에 [단어 안내] 섹션이 함께 주어졌다면, 거기 적힌 두 단어는
   완전히 같은 것으로 취급합니다. 예를 들어 [단어 안내]에 "'크록스'는
   '슬리퍼'와 같은 의미로 취급합니다"라고 되어 있다면, Context에 "크록스"
   라는 글자가 없고 "슬리퍼"만 있어도 이는 "찾을 수 없는 내용"이 아니라
   질문에 대한 답이 되는 내용입니다. 이 경우 규칙 4로 넘어가지 말고, 답변
   에서는 Context의 표현(예: "슬리퍼")을 그대로 쓰지 말고 질문이 쓴 단어
   (예: "크록스")로 바꿔서 답합니다.
3. Context에 질문 주제와 관련된 조항이 있지만, 그 조항이 구체적인 절차나
   기준 대신 "다른 규정(예: 학업성적관리규정)에 따른다"처럼 다른 문서로
   위임하고 있을 뿐이라면, 그 사실을 그대로 전달합니다. 이때는 "해당
   내용은 제공된 학칙에서 찾을 수 없습니다"라는 문구를 절대 쓰지 않고,
   곧바로 "학칙에는 OO 규정을 따른다고만 되어 있고 구체적인 절차는
   나와 있지 않습니다"처럼 있는 그대로만 안내합니다. (관련 조항을
   찾은 것이므로 "찾을 수 없다"는 표현과 함께 쓰면 안 됩니다)
4. Context 안에 질문 주제와 관련된 내용이 전혀 없을 때(3번의 "다른
   규정으로 위임"조차 없을 때)만 아래 형식으로 답합니다.
   - 먼저 "해당 내용은 제공된 학칙에서 찾을 수 없습니다."라고 말합니다.
   - 이어서, 질문 내용에 따라 문의하면 좋을 곳(예: 담임 선생님, 학생부,
     교무실, 행정실 등 질문 주제와 어울리는 곳)을 한 곳 추천합니다.
   - 질문이 너무 모호하거나 범위가 넓어서 못 찾았을 수도 있다면,
     조금 더 구체적으로 다시 질문해 볼 것을 제안합니다.
   - 이 안내 문장들은 실제 학칙 조항이 아니라 일반적인 안내이므로,
     학칙 조항인 것처럼 단정적으로 말하지 않습니다.
5. 위 2, 3번처럼 Context를 근거로 답할 때도, Context에 실제로 없는
   숫자·기간·조건을 새로 만들어내지 않습니다 (근거는 항상 Context).
"""
    system_prompt = sanitize_text(system_prompt)

    synonym_section = f"\n[단어 안내]\n{safe_synonym_note}\n" if safe_synonym_note else ""
    user_prompt = f"""
[학칙 관련 내용]
{safe_context if safe_context else "(없음)"}
{synonym_section}
[질문]
{safe_question}
"""
    user_prompt = sanitize_text(user_prompt)

    # 직전 대화 턴들을 실제 user/assistant 메시지로 풀어 넣는다.
    # (Context는 이번 턴의 user_prompt에만 포함하므로, 과거 턴에는
    #  그때의 질문/답변 텍스트만 넣는다)
    history_messages = []
    for turn in (history or []):
        history_messages.append({"role": "user", "content": sanitize_text(turn.get("question", ""))})
        history_messages.append({"role": "assistant", "content": sanitize_text(turn.get("answer", ""))})

    messages = [
        {"role": "system", "content": system_prompt},
        *history_messages,
        {"role": "user", "content": user_prompt},
    ]
    return _chat(messages, temperature=0.3)


def simple_completion(prompt: str) -> str:
    """
    시스템 프롬프트 없이 사용자 프롬프트 하나만 전달하는 간단한 호출 함수.

    score.py가 "LLM 스스로 답변을 평가"할 때, 별도의 대화 맥락 없이
    평가용 프롬프트 하나만 보내면 되므로 이 함수를 재사용한다.
    클라이언트 설정(base_url, api_key, model)을 한 곳(llm.py)에서만
    관리하기 위해, score.py는 openai 클라이언트를 직접 만들지 않고
    이 함수를 통해서만 LLM을 호출한다.

    Parameters:
        prompt (str): LLM에 전달할 프롬프트 전체 텍스트

    Returns:
        str: LLM의 답변 텍스트
    """
    safe_prompt = sanitize_text(prompt)
    messages = [{"role": "user", "content": safe_prompt}]
    return _chat(messages, temperature=0.0)