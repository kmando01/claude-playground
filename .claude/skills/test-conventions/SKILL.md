---
name: test-conventions
description: Use when writing tests for Spring Boot services - defines unit test and integration test rules, naming conventions, and structure
---

# Test Conventions

Spring Boot 프로젝트의 테스트 작성 규칙을 정의한다.

**핵심 원칙:** 단위 테스트로 빠른 피드백, 통합 테스트로 실제 동작 보장.

## 테스트 피라미드

```
        /  E2E  \          ← 적게 (느림, 비쌈)
       /----------\
      / Integration \      ← 중간
     /----------------\
    /    Unit Tests    \   ← 많이 (빠름, 저렴)
```

## 단위 테스트 (Unit Test)

**대상:** Service 레이어
**위치:** `src/test/kotlin/.../service/`
**네이밍:** `{클래스명}Test.kt`

### 규칙

```kotlin
@ExtendWith(MockitoExtension::class)  // 또는 MockKExtension
class UserServiceTest {

    @Mock  // 또는 @MockK
    lateinit var userRepository: UserRepository

    @InjectMocks  // 또는 직접 생성
    lateinit var userService: UserService

    @Test
    fun `should return user when found by id`() {
        // Given
        val entity = UserEntity(id = 1, name = "홍길동", email = "hong@test.com")
        whenever(userRepository.findById(1L)).thenReturn(Optional.of(entity))

        // When
        val result = userService.getById(1L)

        // Then
        assertEquals("홍길동", result.name)
    }

    @Test
    fun `should throw when user not found`() {
        // Given
        whenever(userRepository.findById(99L)).thenReturn(Optional.empty())

        // When & Then
        assertThrows<NoSuchElementException> {
            userService.getById(99L)
        }
    }
}
```

**필수 규칙:**
- 메서드명: 백틱 + `should {기대결과} when {조건}`
- 구조: Given / When / Then 주석으로 구분
- Mock: 외부 의존성(Repository, 외부 API)만 Mock
- 검증: `verify()`로 호출 여부 확인
- 독립성: 테스트 간 상태 공유 금지

## 통합 테스트 (Integration Test)

**대상:** Controller 레이어 (API 엔드포인트)
**위치:** `src/test/kotlin/.../controller/`
**네이밍:** `{클래스명}IntegrationTest.kt`

### 규칙

```kotlin
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureMockMvc
class UserControllerIntegrationTest {

    @Autowired
    lateinit var mockMvc: MockMvc

    @Autowired
    lateinit var objectMapper: ObjectMapper

    @Autowired
    lateinit var userRepository: UserRepository

    @BeforeEach
    fun setUp() {
        userRepository.deleteAll()
    }

    @Test
    fun `POST api users should create user and return 201`() {
        val request = CreateUserRequest(name = "홍길동", email = "hong@test.com")

        mockMvc.perform(
            post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(request))
        )
            .andExpect(status().isCreated)
            .andExpect(jsonPath("$.name").value("홍길동"))
    }

    @Test
    fun `POST api users should return 400 when name is blank`() {
        val request = CreateUserRequest(name = "", email = "hong@test.com")

        mockMvc.perform(
            post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(request))
        )
            .andExpect(status().isBadRequest)
    }
}
```

**필수 규칙:**
- 실제 DB 사용 (H2 in-memory 또는 Testcontainers)
- `@BeforeEach`로 데이터 초기화
- HTTP 상태 코드 검증 필수
- 요청/응답 본문 검증
- Validation 실패 케이스 포함

## 어떤 테스트를 작성할지

| 상황 | 테스트 유형 |
|------|------------|
| 비즈니스 로직 (계산, 분기) | 단위 테스트 |
| Repository 커스텀 쿼리 | 통합 테스트 (@DataJpaTest) |
| API 엔드포인트 동작 | 통합 테스트 (MockMvc) |
| Validation 규칙 | 통합 테스트 (400 응답 확인) |
| 에러 핸들링 | 단위 + 통합 |

## 테스트 커버리지 기준

| 항목 | 최소 기준 |
|------|----------|
| Service 메서드 | 성공 + 실패 각 1개 이상 |
| Controller 엔드포인트 | 정상 + validation 실패 각 1개 이상 |
| 커스텀 Repository | 쿼리당 1개 이상 |

## Common Mistakes

| 실수 | 해결 |
|------|------|
| 통합 테스트에서 Mock 남용 | 통합 테스트는 실제 빈 사용 |
| 단위 테스트에서 @SpringBootTest | 단위 테스트는 Mock만, 스프링 컨텍스트 불필요 |
| 테스트 간 데이터 오염 | @BeforeEach로 초기화 |
| 성공 케이스만 테스트 | 실패/예외 케이스 필수 |
| 테스트 이름이 불명확 | `should {결과} when {조건}` 형식 |
