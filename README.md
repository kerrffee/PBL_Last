# 학교 학칙 Q&A 챗봇

`data/school_rules.pdf` 문서를 근거로 답변하는 문서 기반 Q&A 챗봇입니다.
Python + Streamlit으로 만들었고, LLM 백엔드는 OpenAI API / Ollama /
기타 OpenAI 호환 서버 중 환경변수 설정만으로 자유롭게 교체할 수 있습니다.

## 폴더 구조

```
project/
├── app.py            # Streamlit 화면 (진입점)
├── knowledge.py       # PDF 텍스트 추출 + 키워드 기반 문장 검색 (get_context)
├── llm.py             # LLM 호출 (질문 + Context 전달, 백엔드 교체 가능)
├── score.py           # LLM 답변의 Confidence Score(0~100) 평가
├── review.py          # 자동 승인(>=80) / 검수 대기(<80) 로직
├── data/
│   └── school_rules.pdf   # 학칙 PDF 원본 (샘플 파일 포함)
├── requirements.txt
├── .env.example
└── README.md
```

## 각 파일의 역할

- **app.py**: 질문 입력, 답변/점수/승인 상태 표시, 검수(수동 승인) 버튼을
  담당하는 Streamlit 화면입니다. `knowledge → llm → score → review` 순서로
  다른 모듈을 호출해 전체 흐름을 조립합니다.
- **knowledge.py**: `data/school_rules.pdf`를 읽어 텍스트를 추출하고,
  문장 단위로 나눈 뒤, 질문과 각 문장의 키워드가 얼마나 겹치는지 계산해
  가장 관련 있는 문장을 Context로 반환합니다 (`get_context(question)`).
  FAISS/ChromaDB/Embedding 없이, 순수 키워드 문자열 매칭으로 동작합니다.
- **llm.py**: `(질문 + Context)`를 하나의 프롬프트로 만들어 LLM에 전달하고
  답변을 받아옵니다. `LLM_BASE_URL`만 바꾸면 OpenAI API든 Ollama든 동일한
  코드로 호출할 수 있습니다.
- **score.py**: LLM에게 자신의 답변을 스스로 평가하게 하여 0~100 사이의
  Confidence Score를 계산합니다.
- **review.py**: Score가 80 이상이면 자동 승인, 미만이면 검수 대기 상태로
  분류하고, 검수 대기 항목을 수동으로 승인 처리하는 함수를 제공합니다.

## 실행 방법 (VS Code 기준)

1. VS Code에서 `project` 폴더를 엽니다.
2. 터미널에서 가상환경을 만들고 활성화합니다.

   ```bash
   python -m venv venv
   source venv/bin/activate      # Windows는 venv\Scripts\activate
   ```

3. 의존성을 설치합니다.

   ```bash
   pip install -r requirements.txt
   ```

4. `.env.example`을 복사해 `.env` 파일을 만들고, 사용할 LLM 정보를 채웁니다.

   ```bash
   cp .env.example .env
   ```

5. `data/school_rules.pdf` 자리에 실제 학칙 PDF를 넣습니다.
   (테스트용 샘플 PDF가 이미 들어 있으므로, 바로 실행해서 동작을 확인할 수도 있습니다.)

6. 앱을 실행합니다.

   ```bash
   streamlit run app.py
   ```

## LLM 백엔드 교체 방법

`llm.py`는 코드를 전혀 수정하지 않고 `.env`의 환경변수만 바꾸면
다른 LLM으로 교체됩니다.

| 사용할 백엔드 | LLM_BASE_URL | LLM_API_KEY | LLM_MODEL |
|---|---|---|---|
| OpenAI 정식 API | `https://api.openai.com/v1` | 실제 API 키 | 예: `gpt-4o-mini` |
| Ollama (로컬) | `http://localhost:11434/v1` | 아무 문자열(예: `ollama`) | 예: `llama3` |
| LM Studio 등 OpenAI 호환 서버 | 해당 서버 주소 + `/v1` | 서버 요구 값 | 로드된 모델 이름 |

Ollama를 사용하려면 Ollama 실행 후 원하는 모델을 미리 받아두어야 합니다.

```bash
ollama pull llama3
ollama serve
```

## 참고 사항

- `knowledge.py`의 문장 검색은 형태소 분석기나 임베딩 없이, 조사(은/는/이/가 등)를
  간단히 제거한 뒤 문자열 포함 여부로 유사도를 계산하는 초보자용 구현입니다.
  실제 서비스에서는 정확도를 높이기 위해 임베딩 기반 검색(FAISS, ChromaDB 등)으로
  교체하는 것을 권장합니다.
- Confidence Score는 LLM 스스로의 자기평가이므로 절대적인 정확도를 보장하지는
  않습니다. 검수 대기(80점 미만) 답변은 반드시 화면에서 사람이 확인 후 승인하세요.
