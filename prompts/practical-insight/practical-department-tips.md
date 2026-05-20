---
name: practical-department-tips
model: claude-sonnet-4-6
version: 1
inputs: [date, departments_json, usecases_json, recent_tips_json]
output_schema: '{"tips": [{"department": "<부서명>", "tip": "<한 줄 팁>"}]}'
---

You generate the **부서별 활용 팁** for an internal weekly AI newsletter aimed
at general employees. For each listed department, write ONE concise Korean tip
(한 줄) on how that department can apply this week's AI use cases to their work.

발행일: {date}

대상 부서(JSON 배열, 각 항목은 부서명과 업무 특성):
{departments_json}

이번 주 활용법 후보(JSON 배열):
{usecases_json}

각 부서가 최근 호에서 이미 안내받은 팁(JSON 객체, 부서명 → 최근 팁 배열):
{recent_tips_json}

규칙:
- 입력 부서마다 정확히 하나의 팁을 작성합니다. 부서명은 입력값 그대로 사용.
- 팁은 이번 주 활용법과 해당 부서의 업무 특성을 매칭한 한 줄(한국어).
- `recent_tips_json`에 이미 있는 팁과 같거나 거의 같은 내용은 반복하지 마세요.
  매주 새로운 각도를 제시합니다.
- 입력에서 직접 도출되는 사실 + 일반 업무 상식만 사용(환각 금지).

아래 JSON만 출력하세요. 다른 설명, 코드 펜스 금지:

{{"tips": [{{"department": "<부서명>", "tip": "<한 줄 팁>"}}]}}
