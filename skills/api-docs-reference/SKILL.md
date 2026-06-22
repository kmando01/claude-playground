---
name: api-docs-reference
description: Spring REST Docs + OpenAPI 3 + Swagger UI API 문서화 레퍼런스. 의존성 설정, 테스트 패턴(POST/GET/페이지네이션/에러), 공통 필드 재사용 유틸 포함. API 문서 작성 시 참조.
---

# API 문서화 레퍼런스

## 방식: REST Docs + OpenAPI 3

```
테스트 코드에서 API 스펙 정의 → OpenAPI 3 JSON 생성 → Swagger UI 제공
→ 프로덕션 코드 깨끗, 테스트 통과 = 문서 정확성 보장
```

## 의존성

```kotlin
// build.gradle.kts (루트)
plugins {
    id("com.epages.restdocs-api-spec") version "0.19.2"
}

// app-api 모듈
plugins {
    id("com.epages.restdocs-api-spec")
}

dependencies {
    testImplementation("org.springframework.restdocs:spring-restdocs-mockmvc")
    testImplementation("com.epages:restdocs-api-spec-mockmvc:0.19.2")
}

openapi3 {
    setServer("http://localhost:8080")
    title = "XXX API"
    description = "XXX 서비스 API 문서"
    version = "1.0.0"
    format = "json"
    outputDirectory = "build/api-spec"
}
```

## Swagger UI 설정

```kotlin
// build.gradle.kts
dependencies {
    implementation("org.webjars:swagger-ui:5.10.3")
}

tasks.register<Copy>("copyOpenApiSpec") {
    dependsOn("openapi3")
    from("build/api-spec/openapi3.json")
    into("src/main/resources/static/docs")
}
```

```kotlin
// SwaggerConfig.kt
@Configuration
class SwaggerConfig : WebMvcConfigurer {
    override fun addResourceHandlers(registry: ResourceHandlerRegistry) {
        registry.addResourceHandler("/docs/**")
            .addResourceLocations("classpath:/static/docs/")
    }
}
```

```
접속 URL:
- Swagger UI: http://localhost:8080/swagger-ui/index.html?url=/docs/openapi3.json
- OpenAPI Spec: http://localhost:8080/docs/openapi3.json
```

## 테스트 기본 구조

```kotlin
@WebMvcTest(OrderController::class)
@AutoConfigureRestDocs
class OrderControllerDocsTest {
    @Autowired
    private lateinit var mockMvc: MockMvc

    @MockkBean
    private lateinit var createOrderUseCase: CreateOrderUseCase

    @MockkBean
    private lateinit var getOrderUseCase: GetOrderUseCase
}
```

## POST API 문서화

```kotlin
@Test
fun `주문 생성 API`() {
    val request = CreateOrderRequest(
        items = listOf(OrderItemRequest(productId = 1, quantity = 2))
    )
    val order = Order(id = 1, userId = 1)
    every { createOrderUseCase.execute(any()) } returns order

    mockMvc.perform(
        post("/api/v1/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content(objectMapper.writeValueAsString(request))
            .header("Authorization", "Bearer test-token")
    )
        .andExpect(status().isOk)
        .andDo(
            MockMvcRestDocumentationWrapper.document(
                identifier = "order-create",
                resourceDetails = ResourceSnippetParametersBuilder()
                    .tag("주문").summary("주문 생성").description("새로운 주문을 생성합니다"),
                snippets = arrayOf(
                    requestHeaders(headerWithName("Authorization").description("인증 토큰")),
                    requestFields(
                        fieldWithPath("items").description("주문 상품 목록"),
                        fieldWithPath("items[].productId").description("상품 ID"),
                        fieldWithPath("items[].quantity").description("수량")
                    ),
                    responseFields(
                        fieldWithPath("success").description("성공 여부"),
                        fieldWithPath("data.id").description("주문 ID"),
                        fieldWithPath("data.status").description("주문 상태"),
                        fieldWithPath("error").description("에러 정보").optional()
                    )
                )
            )
        )
}
```

## GET API 문서화

```kotlin
@Test
fun `주문 단건 조회 API`() {
    val order = Order(id = 1, userId = 1)
    every { getOrderUseCase.execute(1L, any()) } returns order

    mockMvc.perform(
        get("/api/v1/orders/{orderId}", 1)
            .header("Authorization", "Bearer test-token")
    )
        .andExpect(status().isOk)
        .andDo(
            MockMvcRestDocumentationWrapper.document(
                identifier = "order-get",
                resourceDetails = ResourceSnippetParametersBuilder()
                    .tag("주문").summary("주문 조회").description("주문 ID로 주문을 조회합니다"),
                snippets = arrayOf(
                    pathParameters(parameterWithName("orderId").description("주문 ID")),
                    responseFields(
                        fieldWithPath("success").description("성공 여부"),
                        fieldWithPath("data.id").description("주문 ID"),
                        fieldWithPath("data.status").description("주문 상태"),
                        fieldWithPath("error").description("에러 정보").optional()
                    )
                )
            )
        )
}
```

## 목록 조회 (페이지네이션)

```kotlin
@Test
fun `주문 목록 조회 API`() {
    every { getOrderListUseCase.execute(any(), any()) } returns PageImpl(listOf())

    mockMvc.perform(
        get("/api/v1/orders")
            .param("page", "0").param("size", "20").param("status", "PENDING")
            .header("Authorization", "Bearer test-token")
    )
        .andExpect(status().isOk)
        .andDo(
            MockMvcRestDocumentationWrapper.document(
                identifier = "order-list",
                resourceDetails = ResourceSnippetParametersBuilder()
                    .tag("주문").summary("주문 목록 조회"),
                snippets = arrayOf(
                    queryParameters(
                        parameterWithName("page").description("페이지 번호 (0부터)").optional(),
                        parameterWithName("size").description("페이지 크기").optional(),
                        parameterWithName("status").description("주문 상태 필터").optional()
                    ),
                    responseFields(
                        fieldWithPath("success").description("성공 여부"),
                        fieldWithPath("data.content[]").description("주문 목록"),
                        fieldWithPath("data.page").description("현재 페이지"),
                        fieldWithPath("data.size").description("페이지 크기"),
                        fieldWithPath("data.totalElements").description("전체 항목 수"),
                        fieldWithPath("data.totalPages").description("전체 페이지 수"),
                        fieldWithPath("error").description("에러 정보").optional()
                    )
                )
            )
        )
}
```

## 에러 응답 문서화

```kotlin
@Test
fun `주문 조회 실패 - 존재하지 않는 주문`() {
    every { getOrderUseCase.execute(999L, any()) } throws DomainException.NotFound("Order", 999)

    mockMvc.perform(get("/api/v1/orders/{orderId}", 999).header("Authorization", "Bearer test-token"))
        .andExpect(status().isNotFound)
        .andDo(
            MockMvcRestDocumentationWrapper.document(
                identifier = "order-get-not-found",
                resourceDetails = ResourceSnippetParametersBuilder()
                    .tag("주문").summary("주문 조회 실패").description("존재하지 않는 주문 조회 시 404 응답"),
                snippets = arrayOf(
                    responseFields(
                        fieldWithPath("success").description("성공 여부 (false)"),
                        fieldWithPath("data").description("null"),
                        fieldWithPath("error.code").description("에러 코드"),
                        fieldWithPath("error.message").description("에러 메시지")
                    )
                )
            )
        )
}
```

## 공통 필드 재사용 유틸

```kotlin
object ApiDocsFields {
    fun successResponseFields(vararg dataFields: FieldDescriptor): List<FieldDescriptor> =
        listOf(
            fieldWithPath("success").description("성공 여부"),
            fieldWithPath("error").description("에러 정보").optional()
        ) + dataFields.toList()

    fun errorResponseFields(): List<FieldDescriptor> = listOf(
        fieldWithPath("success").description("성공 여부 (false)"),
        fieldWithPath("data").description("null").optional(),
        fieldWithPath("error.code").description("에러 코드"),
        fieldWithPath("error.message").description("에러 메시지")
    )

    fun pageResponseFields(prefix: String, vararg contentFields: FieldDescriptor): List<FieldDescriptor> =
        listOf(
            fieldWithPath("success").description("성공 여부"),
            fieldWithPath("$prefix.page").description("현재 페이지"),
            fieldWithPath("$prefix.size").description("페이지 크기"),
            fieldWithPath("$prefix.totalElements").description("전체 항목 수"),
            fieldWithPath("$prefix.totalPages").description("전체 페이지 수"),
            fieldWithPath("error").description("에러 정보").optional()
        ) + contentFields.toList()
}
```

## 테스트 파일 위치

```
xxx-app-api/src/test/kotlin/com/xxx/api/{도메인명}/
├── controller/
│   └── {Domain}ControllerTest.kt      # 기능 테스트
└── docs/
    └── {Domain}ControllerDocsTest.kt   # API 문서 테스트
```

## 문서 생성 명령어

```bash
./gradlew :xxx-app-api:openapi3          # 테스트 + OpenAPI 3 생성
./gradlew :xxx-app-api:copyOpenApiSpec   # Swagger UI용 복사
```
