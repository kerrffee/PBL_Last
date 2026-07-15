"""
review.py
--------------------------------------------------------
Confidence Score를 기준으로 답변을 자동 승인할지, 사람이
검수해야 할지를 결정하고, 검수(수동 승인) 로직을 담당하는
모듈입니다.

[기능 추가] 검수자가 "수정 후 승인"한 질문/답변은 data/reviewed_answers.json
파일에 저장해 둔다. 같은(또는 문장부호만 다른) 질문이 다시 들어오면
knowledge.py/llm.py를 다시 거치지 않고 이 저장된 답변을 그대로 재사용한다.
(app.py의 handle_question()이 매 질문마다 find_learned_answer()를 먼저
확인한다) 이렇게 하면 검수자가 한 번 고친 내용이 이후 같은 질문에 계속
반영된다.

주의: Streamlit Community Cloud처럼 디스크가 영구적이지 않은 환경에서는
앱이 재시작/재배포될 때 이 파일도 초기화될 수 있다. 로컬 실행이나 같은
컨테이너가 살아있는 동안에는 정상적으로 누적된다.
--------------------------------------------------------
"""

import json
import os

# 자동 승인 기준 점수 (요구사항: score >= 80 이면 자동 승인)
CONFIDENCE_THRESHOLD = 80

# 화면에 표시할 상태 문자열들을 상수로 정의해, app.py 여러 곳에서
# 오타 없이 동일한 문자열을 재사용할 수 있게 한다.
STATUS_APPROVED = "자동 승인"
STATUS_PENDING = "검수 대기"
STATUS_MANUALLY_APPROVED = "검수 승인 완료"
STATUS_REJECTED = "반려됨"
STATUS_LEARNED = "이전 검수 답변 재사용"

# 검수자가 "수정 후 승인"한 질문/답변을 저장해 두는 파일 경로.
# (VS Code 등 어떤 위치에서 실행하더라도 항상 이 파일 기준 상대경로를 쓴다)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEARNED_ANSWERS_PATH = os.path.join(BASE_DIR, "data", "reviewed_answers.json")


def decide_status(score: int) -> str:
    """
    Confidence Score를 기준으로 답변의 초기 상태를 결정한다.

    Parameters:
        score (int): score.evaluate_confidence()가 계산한 Confidence Score (0~100)

    Returns:
        str: score가 CONFIDENCE_THRESHOLD 이상이면 STATUS_APPROVED,
             미만이면 STATUS_PENDING
    """
    if score >= CONFIDENCE_THRESHOLD:
        return STATUS_APPROVED
    return STATUS_PENDING


def is_pending(item: dict) -> bool:
    """
    해당 Q&A 항목이 아직 검수 대기 상태인지 확인하는 헬퍼 함수.
    app.py가 화면에 '승인' 버튼을 보여줄지 판단할 때 사용한다.

    Parameters:
        item (dict): {"question", "context", "answer", "score", "status"} 형태의
                     Q&A 기록 하나

    Returns:
        bool: 검수 대기 상태이면 True, 아니면 False
    """
    return item.get("status") == STATUS_PENDING


def _normalize_question(question: str) -> str:
    """
    저장된 질문과 새로 들어온 질문을 비교하기 쉽도록 정규화한다.

    "휴학은 어떻게 신청하나요?"와 "휴학은 어떻게 신청하나요?  " 처럼
    앞뒤 공백이나 문장 끝의 물음표/마침표 유무 같은 사소한 차이는
    같은 질문으로 인식하기 위해, 앞뒤 공백과 흔한 문장부호를 제거한다.
    (완전히 다른 표현으로 바꿔 쓴 질문까지 같다고 인식하지는 않는다 -
    knowledge.py처럼 오탐을 만들지 않기 위해 일부러 단순하게 유지한다)

    Parameters:
        question (str): 원본 질문

    Returns:
        str: 비교용으로 정규화된 질문 문자열
    """
    return question.strip().strip("?!. ")


def _load_learned_answers() -> dict:
    """
    data/reviewed_answers.json 파일을 읽어 저장된 질문/답변 목록을 반환한다.
    파일이 없거나 읽기에 실패하면 빈 dict를 반환한다.

    Returns:
        dict[str, dict]: {정규화된 질문: {"question": 원본 질문, "answer": 답변}}
    """
    if not os.path.exists(LEARNED_ANSWERS_PATH):
        return {}
    try:
        with open(LEARNED_ANSWERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_learned_answers(data: dict) -> None:
    """dict 전체를 data/reviewed_answers.json 파일에 저장(덮어쓰기)한다."""
    os.makedirs(os.path.dirname(LEARNED_ANSWERS_PATH), exist_ok=True)
    with open(LEARNED_ANSWERS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_learned_answer(question: str, answer: str) -> None:
    """
    검수자가 "수정 후 승인"한 질문/답변을 파일에 저장한다.
    이후 find_learned_answer()가 같은 질문에 대해 이 답변을 재사용한다.

    Parameters:
        question (str): 사용자가 입력했던 원본 질문
        answer (str): 검수자가 수정해서 승인한 최종 답변
    """
    data = _load_learned_answers()
    data[_normalize_question(question)] = {"question": question, "answer": answer}
    _save_learned_answers(data)


def find_learned_answer(question: str):
    """
    이전에 검수자가 "수정 후 승인"한 적 있는 질문인지 확인한다.
    app.py가 knowledge/llm을 호출하기 전에 먼저 이 함수를 확인해서,
    이미 검수된 답변이 있으면 그걸 그대로 재사용한다.

    Parameters:
        question (str): 사용자가 입력한 질문

    Returns:
        str | None: 저장된 답변이 있으면 그 문자열, 없으면 None
    """
    entry = _load_learned_answers().get(_normalize_question(question))
    return entry["answer"] if entry else None


def approve_manually(item: dict) -> dict:
    """
    검수 대기 중인 답변을 수정 없이 그대로 사람이 승인 처리한다.
    app.py에서 '이대로 승인' 버튼을 눌렀을 때 호출된다.

    Parameters:
        item (dict): 검수 대기 상태인 Q&A 기록 하나 (app.py의
                     st.session_state.history 안의 항목)

    Returns:
        dict: status가 STATUS_MANUALLY_APPROVED로 변경된 item
              (item은 dict이므로 참조가 그대로 유지되어, app.py의
              session_state.history 안 값도 함께 변경된다)
    """
    item["status"] = STATUS_MANUALLY_APPROVED
    return item


def edit_and_approve(item: dict, edited_answer: str) -> dict:
    """
    검수자가 답변 내용을 직접 고친 뒤 승인 처리한다.
    app.py에서 '수정 후 승인' 버튼을 눌렀을 때 호출된다.

    수정 전 원본 답변은 item["original_answer"]에 남겨 두어, 나중에
    "LLM이 원래 뭐라고 답했는지"를 검수 기록에서 확인할 수 있게 한다.

    Parameters:
        item (dict): 검수 대기 상태인 Q&A 기록 하나
        edited_answer (str): 검수자가 수정한 답변 텍스트

    Returns:
        dict: answer가 edited_answer로, status가 STATUS_MANUALLY_APPROVED로
              바뀌고 edited=True가 표시된 item
    """
    item["original_answer"] = item["answer"]
    item["answer"] = edited_answer
    item["status"] = STATUS_MANUALLY_APPROVED
    item["edited"] = True
    save_learned_answer(item["question"], edited_answer)
    return item


def reject_manually(item: dict) -> dict:
    """
    검수 대기 중인 답변을 사람이 직접 반려 처리한다.
    app.py에서 '반려' 버튼을 눌렀을 때 호출된다.

    반려는 답변을 고쳐서 쓰기보다, 아예 신뢰할 수 없다고 판단해
    사용하지 않기로 결정하는 액션이다. (수정 후 승인과 구분됨)

    Parameters:
        item (dict): 검수 대기 상태인 Q&A 기록 하나

    Returns:
        dict: status가 STATUS_REJECTED로 변경된 item
    """
    item["status"] = STATUS_REJECTED
    return item
