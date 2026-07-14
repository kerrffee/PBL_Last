"""
score.py
--------------------------------------------------------
LLM이 자기 자신의 답변을 스스로 평가하여
Confidence Score(0~100)를 생성하는 모듈입니다.

llm.py의 simple_completion()을 재사용하므로, LLM 클라이언트
설정(base_url, api_key, model)을 이 파일에서 따로 관리하지
않는다. (설정은 llm.py 한 곳에서만 관리)
--------------------------------------------------------
"""

import re
from llm import simple_completion

# LLM이 점수를 정상적으로 반환하지 못했을 때(파싱 실패 등) 사용할 안전한 기본 점수.
# 기본값을 임계값(80)보다 낮게 두어, 애매한 경우 자동승인 대신 사람이
# 검수하도록 보수적으로(안전하게) 처리한다.
DEFAULT_SCORE = 50


def build_evaluation_prompt(question: str, answer: str) -> str:
    """
    LLM에게 스스로 생성한 답변을 평가하도록 요청하는 프롬프트를 만든다.

    Parameters:
        question (str): 사용자 질문
        answer (str): LLM이 생성한 답변

    Returns:
        str: 평가용 프롬프트 문자열
    """
    return (
        "다음은 학교 학칙 챗봇의 질문과 답변입니다.\n\n"
        f"[질문]\n{question}\n\n"
        f"[답변]\n{answer}\n\n"
        "이 답변이 학칙 내용에 근거하여 얼마나 정확하고 신뢰할 수 있게 "
        "작성되었는지 0부터 100 사이의 숫자 하나로만 평가해 주세요. "
        "숫자가 높을수록 신뢰도가 높다는 뜻입니다. "
        "다른 설명 없이 숫자만 출력하세요. 예시: 85"
    )


def parse_score(llm_output: str) -> int:
    """
    LLM의 응답 텍스트에서 0~100 사이의 정수 점수만 추출한다.

    LLM이 "85점입니다"처럼 부가 설명을 붙여서 답하는 경우에도
    정규식으로 숫자만 뽑아낸다.

    Parameters:
        llm_output (str): LLM이 반환한 원본 텍스트

    Returns:
        int: 추출된 점수 (0~100). 숫자를 찾지 못하면 DEFAULT_SCORE를 반환한다.
    """
    match = re.search(r"\d+", llm_output)
    if not match:
        return DEFAULT_SCORE

    score = int(match.group())
    # 혹시 LLM이 100보다 크거나 음수를 준 경우를 대비해 0~100 범위로 잘라낸다.
    score = max(0, min(100, score))
    return score


def evaluate_confidence(question: str, answer: str) -> int:
    """
    질문과 답변을 바탕으로 LLM에게 Confidence Score를 요청하고,
    파싱된 정수 점수를 반환하는 메인 함수.

    app.py는 이 함수가 반환한 점수를 review.decide_status()에 전달하여
    자동 승인 여부를 결정한다.

    Parameters:
        question (str): 사용자 질문
        answer (str): llm.generate_answer()가 생성한 답변

    Returns:
        int: 0~100 사이의 Confidence Score
    """
    prompt = build_evaluation_prompt(question, answer)
    raw_output = simple_completion(prompt)
    return parse_score(raw_output)
