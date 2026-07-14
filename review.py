"""
review.py
--------------------------------------------------------
Confidence Score를 기준으로 답변을 자동 승인할지, 사람이
검수해야 할지를 결정하고, 검수(수동 승인) 로직을 담당하는
모듈입니다.
--------------------------------------------------------
"""

# 자동 승인 기준 점수 (요구사항: score >= 80 이면 자동 승인)
CONFIDENCE_THRESHOLD = 80

# 화면에 표시할 상태 문자열들을 상수로 정의해, app.py 여러 곳에서
# 오타 없이 동일한 문자열을 재사용할 수 있게 한다.
STATUS_APPROVED = "자동 승인"
STATUS_PENDING = "검수 대기"
STATUS_MANUALLY_APPROVED = "검수 승인 완료"
STATUS_REJECTED = "반려됨"


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
