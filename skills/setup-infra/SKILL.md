---
name: setup-infra
description: Use when setting up local development infrastructure with Docker, adding new infrastructure components like DB or Redis, or when the user says "인프라 세팅해줘" or "Docker 환경 만들어줘"
---

# Setup Local Infrastructure

Docker Compose로 로컬 개발 인프라를 구성한다.

**핵심 원칙:** docker compose up -d 한 줄로 전체 로컬 환경이 실행되어야 한다.

## Process

### Step 1: 인프라 요구사항 파악

$ARGUMENTS 또는 프로젝트를 분석해서 필요한 인프라 식별:

| 컴포넌트 | 언제 필요 |
|----------|----------|
| MySQL/PostgreSQL | JPA 사용 시 (필수) |
| Redis | 캐싱, 세션 스토어 |
| RabbitMQ/Kafka | 메시지 큐, 이벤트 드리븐 |
| Elasticsearch | 검색 기능 |
| MinIO | 파일 스토리지 (S3 호환) |

### Step 2: Dockerfile 생성

```dockerfile
# 멀티스테이지 빌드
FROM gradle:8-jdk21 AS build
WORKDIR /app
COPY . .
RUN gradle build -x test --no-daemon

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/build/libs/*.jar app.jar
RUN addgroup --system appuser && adduser --system --ingroup appuser appuser
USER appuser
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
```

**필수 규칙:**
- 멀티스테이지 빌드 (빌드 이미지 ≠ 런타임 이미지)
- non-root user
- .dockerignore 생성

### Step 3: docker-compose.yml 생성

```yaml
services:
  app:
    build: .
    ports:
      - "8080:8080"
    depends_on:
      db:
        condition: service_healthy
    environment:
      SPRING_PROFILES_ACTIVE: docker

  db:
    image: mysql:8.0
    ports:
      - "3306:3306"
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: appdb
    volumes:
      - db-data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      retries: 5

volumes:
  db-data:
```

**필수 규칙:**
- depends_on + healthcheck로 실행 순서 보장
- volume으로 데이터 영속화
- 환경변수로 설정 주입
- 포트 충돌 방지 (호스트 포트 확인)

### Step 4: Spring 프로파일 분리

application.yml (기본) + application-docker.yml (Docker용):

```yaml
# application-docker.yml
spring:
  datasource:
    url: jdbc:mysql://db:3306/appdb
    username: root
    password: root
```

### Step 5: 검증

```bash
docker compose up -d        # 인프라 실행
docker compose ps            # 상태 확인
docker compose logs app      # 앱 로그 확인
curl localhost:8080/api/health  # 헬스체크
```

## Quick Reference

```bash
docker compose up -d         # 전체 실행
docker compose down          # 전체 중지
docker compose down -v       # 중지 + 볼륨 삭제 (데이터 초기화)
docker compose logs -f app   # 앱 로그 실시간
docker compose restart app   # 앱만 재시작
```
