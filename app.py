"""
app.py
--------------------------------------------------------
Streamlit 메인 화면 (진입점).

전체 흐름:
1. 사용자가 질문을 입력한다.
2. knowledge.py로 학칙 PDF(data/school_rules.pdf)에서
   질문과 가장 관련 있는 문장(Context)을 찾는다.
3. llm.py로 (질문 + Context)를 함께 전달해 답변을 생성한다.
4. score.py로 답변의 Confidence Score(0~100)를 계산한다.
5. review.py로 자동 승인(>=80) / 검수 대기(<80) 여부를 결정한다.
6. 검수 대기 항목은 화면에서 사람이 직접 승인할 수 있다.

이 파일은 화면(UI) 구성과 각 모듈 호출 순서만 담당하며,
LLM 호출 방식이나 유사도 계산 로직은 직접 갖고 있지 않는다.
--------------------------------------------------------
"""

import streamlit as st

import knowledge
import llm
import score
import review

st.set_page_config(page_title="학교 학칙 Q&A 챗봇", page_icon="📘")
st.title("📘 학교 학칙 Q&A 챗봇")
st.caption("data/school_rules.md 문서를 근거로 답변하는 문서 기반 Q&A 챗봇입니다.")

# 대화 기록을 세션 상태에 저장한다. Streamlit은 사용자가 상호작용할 때마다
# 스크립트 전체를 다시 실행하므로, session_state에 저장하지 않으면
# 이전 질문/답변 기록이 매번 사라진다.
if "history" not in st.session_state:
    st.session_state.history = []


def handle_question(question: str) -> None:
    """
    사용자가 질문을 제출했을 때 전체 파이프라인을 실행하는 함수.

    knowledge -> llm -> score -> review 순서로 각 모듈을 호출하고,
    결과를 st.session_state.history에 새 항목으로 추가한다.

    다만 그 전에, 검수자가 예전에 이 질문을 "수정 후 승인"한 적이 있는지
    먼저 확인한다(review.find_learned_answer). 있다면 knowledge/llm을
    다시 거치지 않고 그 답변을 바로 재사용한다 - 검수자가 한 번 고친
    내용이 다음에 같은 질문에도 반영되게 하기 위함이다.

    Parameters:
        question (str): 사용자가 입력한 질문
    """
    # 0) 이전에 검수자가 고쳐서 승인한 적 있는 질문이면, 그 답변을 그대로 재사용한다.
    learned_answer = review.find_learned_answer(question)
    if learned_answer is not None:
        st.session_state.history.append({
            "question": question,
            "context": "(이전에 검수자가 확인한 답변이라 학칙을 다시 검색하지 않았습니다.)",
            "answer": learned_answer,
            "score": 100,
            "status": review.STATUS_LEARNED,
        })
        return

    # 1) 학칙 Markdown 문서에서 질문과 가장 관련 있는 문장(Context)을 찾는다.
    with st.spinner("학칙에서 관련 내용을 찾는 중..."):
        context = knowledge.get_context(question)
        print("===== CONTEXT =====")
        print(context)
        print("===================")

    # 2) 질문 + Context를 함께 LLM에 전달해 답변을 생성한다.
    with st.spinner("답변을 생성하는 중..."):
        answer = llm.generate_answer(question, context)

    # 3) LLM이 스스로 답변의 신뢰도(Confidence Score)를 평가한다.
    with st.spinner("답변의 신뢰도를 평가하는 중..."):
        confidence = score.evaluate_confidence(question, answer)

    # 4) 점수를 기준으로 자동 승인 / 검수 대기 상태를 결정한다.
    status = review.decide_status(confidence)

    st.session_state.history.append({
        "question": question,
        "context": context,
        "answer": answer,
        "score": confidence,
        "status": status,
    })


# ---------------- 질문 입력 영역 ----------------
with st.form("question_form", clear_on_submit=True):
    question_input = st.text_input("학칙에 대해 궁금한 점을 입력하세요.")
    submitted = st.form_submit_button("질문하기")

if submitted and question_input.strip():
    handle_question(question_input.strip())

st.divider()

# ---------------- 대화 기록 / 검수 화면 ----------------
if not st.session_state.history:
    st.info("아직 질문 기록이 없습니다. 위에 질문을 입력해 보세요.")

# 최신 질문이 위쪽에 표시되도록 역순으로 순회한다.
for idx, item in reversed(list(enumerate(st.session_state.history))):
    with st.container(border=True):
        st.markdown(f"**Q. {item['question']}**")
        st.write(item["answer"])
        if item.get("edited"):
            st.caption("✏️ 검수자가 답변을 수정했습니다.")

        col1, col2 = st.columns(2)
        col1.metric("Confidence Score", f"{item['score']} / 100")
        col1.progress(item["score"] / 100)

        if item["status"] in (review.STATUS_APPROVED, review.STATUS_MANUALLY_APPROVED, review.STATUS_LEARNED):
            col2.success(item["status"])
        elif item["status"] == review.STATUS_REJECTED:
            col2.error(item["status"])
        else:
            col2.warning(item["status"])

        # knowledge.py가 찾아낸 학칙 원문을 펼쳐서 확인할 수 있게 한다 (근거 확인용).
        with st.expander("📄 참고한 학칙 원문(Context) 보기"):
            st.write(item["context"] if item["context"] else "관련 문장을 찾지 못했습니다.")

        # 수정 후 승인한 경우, 검수자가 원래 답변과 비교해볼 수 있게 남겨둔다.
        if item.get("original_answer"):
            with st.expander("🕓 수정 전 원래 답변 보기"):
                st.write(item["original_answer"])

        # 검수 대기 상태인 항목에만 승인/수정/반려 액션을 노출한다.
        if review.is_pending(item):
            edited_answer = st.text_area(
                "필요하면 답변을 고친 뒤 승인하세요.",
                value=item["answer"],
                key=f"edit_{idx}",
            )

            col_approve, col_edit, col_reject = st.columns(3)
            if col_approve.button("✅ 이대로 승인", key=f"approve_{idx}"):
                review.approve_manually(item)
                st.rerun()
            if col_edit.button("✏️ 수정 후 승인", key=f"edit_approve_{idx}"):
                review.edit_and_approve(item, edited_answer)
                st.rerun()
            if col_reject.button("❌ 반려", key=f"reject_{idx}"):
                review.reject_manually(item)
                st.rerun()
