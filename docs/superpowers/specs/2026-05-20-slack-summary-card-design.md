# Slack 요약 카드 발송 — 설계

> Phase 2 항목 "Slack 요약 발송"(`plan/ai_newsletter_service_plan.md` §25, §9.1).
> 작성일: 2026-05-20. 상태: 승인됨.

## 목적

승인된 뉴스레터 이슈를 이메일 외에 Slack 채널로도 **요약 카드** 형태로
배포한다. 이메일은 전체 본문을, Slack은 제목 + 핵심 하이라이트 + 아카이브
링크를 담은 경량 카드를 보낸다. 추가 LLM 호출 없이 기존 이슈 필드에서
결정적으로 카드를 구성한다.

## 범위 결정 (브레인스토밍 합의)

- **콘텐츠**: 요약 카드 (전체 본문/LLM 재요약 아님).
- **인증**: Slack Incoming Webhook (단일 URL, 고정 채널). Bot token 아님.
- **발송 흐름**: 이메일과 독립된 채널 명령. `status`를 변경하지 않는다
  (이메일 발송이 `sent` 전환을 소유). `slack_sent_at` 컬럼만 기록.
- **상태 가드**: `approved` 상태에서만 발송 (CLAUDE.md 하드룰). `--force` 없음
  으로는 상태 가드를 우회할 수 없다.

## 아키텍처

distribution 슬라이스에 추가한다. 새 슬라이스를 만들지 않는다 — Slack은
이메일과 같은 "배포" 책임이다. Notion 아카이브 슬라이스의 패턴
(httpx 클라이언트 + `from_settings()` None 폴백 + 주입 가능한 http_client +
상태 가드 + dry-run + `record_step`)을 그대로 따른다.

```
src/newsletter/slices/distribution/
  slack_client.py   # NEW — httpx 기반 Incoming Webhook POST 래퍼
  slack.py          # NEW — post_issue_to_slack() 서비스 (approved 가드 + 멱등)
  card.py           # NEW — 이슈 → Block Kit 카드(dict) 빌더 (순수 함수, LLM 없음)
  cli.py            # 확장 — `slack` 서브커맨드
  sender.py / service.py   # 변경 없음 (이메일 그대로)
```

## 데이터 흐름

```
newsletter slack --issue ID [--dry-run] [--force]
  → NewsletterIssue 조회 (없으면 exit 1)
  → 가드: status == "approved" 아니면 SlackSendError
  → 가드: slack_sent_at 이미 있고 not force 면 AlreadySentError
  → card.build_card(issue): Block Kit blocks(list[dict])
  → dry_run 이면 카드 dict 만 로그/echo 후 종료 (POST 안 함)
  → SlackClient.post(blocks)
  → issue.slack_sent_at = now(UTC); session.flush()
  → record_step("slack", meta={issue_id, dry_run}) 로 모니터링 기록
```

`status` 전환 없음. `slack_sent_at`은 이메일 `sent_at`·아카이브 `archived_at`과
동형 컬럼이다.

## 카드 콘텐츠 (Block Kit, 순수 함수 `card.build_card`)

- header: `📰 {issue.title}`
- context: 발행일(`issue_date`) + audience(`issue.audience or "general"`)
- 하이라이트 섹션: `markdown_body`에서 `^#### ` 로 시작하는 라인 추출 →
  `#### ` 접두어 제거 → 최대 `max_highlights`(기본 5)개를 bullet 으로 묶음.
  `####` 헤드라인이 하나도 없으면 첫 비-헤딩·비-빈 텍스트 N줄로 폴백.
- 링크 버튼: `notion_page_id`가 있을 때만 "아카이브에서 보기" 버튼 →
  `https://www.notion.so/{notion_page_id에서 대시 제거}`. 없으면 버튼 생략.

`build_card`는 DB·네트워크에 의존하지 않는 순수 함수다(이슈 dataclass/모델
인스턴스만 입력).

## 설정 (`core/config.py`)

- `slack_webhook_url: str = Field(default="", description="Slack Incoming Webhook URL")`

`SlackClient.from_settings()`는 `slack_webhook_url`이 비어 있으면 `None`을
반환한다(아카이브의 `NotionClient.from_settings()` 패턴).

## 모델 / 마이그레이션

- `NewsletterIssue.slack_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))`
- Alembic autogenerate 마이그레이션 1건.

## 에러 처리

Notion 슬라이스 예외 네이밍과 동형:

| 예외 | 발생 조건 |
|---|---|
| `SlackError` | 클라이언트: 네트워크 실패, 4xx/5xx 응답 |
| `SlackDisabledError` | 서비스가 `client=None`(미설정)을 받음 |
| `SlackSendError` | 상태 가드 위반(approved 아님), webhook URL 부재 |
| `AlreadySentError` | `slack_sent_at` 이미 있음 + `force=False` |

## 테스트 (TDD, 실제 외부 호출 없음)

- `card.py` (순수 함수): `####` 헤드라인 추출 / 최대 개수 cap / 헤드라인 없을 때
  폴백 / notion_page_id 유무에 따른 링크 버튼 / header·context 구성.
- `slack.py` (fake client 주입): approved 아니면 거부 / `client=None` 거부 /
  `slack_sent_at` 멱등(force로 우회) / dry-run은 POST 호출 안 함 / 성공 시
  `slack_sent_at` 기록.
- `slack_client.py` (respx 모킹): webhook POST 성공 / 4xx → `SlackError` /
  네트워크 에러 → `SlackError` / `from_settings()` None 폴백.

## 미적용 (YAGNI)

- Bot token / 다중 채널 / 스레드 / 메시지 업데이트.
- LLM 재요약.
- Slack에서의 상태 전환 또는 승인 트리거.
