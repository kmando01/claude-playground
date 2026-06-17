# API 문서화

## 핵심 원칙
- MUST: Spring REST Docs 테스트 기반으로 API 문서 생성 (SpringDoc 금지)
- MUST: restdocs-api-spec → OpenAPI 3 → Swagger UI 파이프라인
- MUST: 모든 public API에 REST Docs 테스트 작성
- MUST: tag로 도메인별 그룹핑, summary/description 한글 작성
- MUST: Request/Response 모든 필드에 description 명시
- MUST: 에러 응답도 문서화 (400, 401, 403, 404, 409)
- MUST: 기능 테스트와 문서 테스트 분리 (`docs/` 패키지)
- SHOULD: enum 필드는 description에 가능한 값 나열
- NEVER: 프로덕션 Controller에 @Tag, @Operation, @Schema 어노테이션 추가 금지
- NEVER: 민감 필드(password, token)를 example에 포함하지 않음

## 상세 가이드
의존성 설정, 테스트 예시(POST/GET/페이지네이션/에러), 공통 필드 재사용 유틸은 `api-docs-reference` 스킬을 참조하라.
