---
name: archunit-testing
description: ArchUnit architecture test patterns for multi-module projects. Use when adding new modules, packages, or domain boundaries. Covers module dependency rules, package isolation, domain purity enforcement, and test writing conventions. Use when user says "아키텍처 테스트", "ArchUnit", "계층 검사", or when modifying module structure.
---

# ArchUnit 아키텍처 테스트 패턴

## 핵심 원칙

- **검증은 2단계** — Gradle 의존성(모듈 레벨) 먼저, ArchUnit(코드 레벨) 다음
- **3방향 정합성 유지** — 실제 코드, 문서 규칙(multi-module.md), ArchUnit 테스트가 일치해야 함
- **규칙도 검증 대상** — 코드가 규칙을 어겼는지뿐 아니라, 규칙이 현실과 맞는지도 판단
- **새 모듈/패키지 추가 시 규칙도 추가** — 경계 없는 코드는 곧 의존성 부패
- **테스트 클래스는 스캔에서 제외** — `ImportOption.DoNotIncludeTests()` 필수

## 검증 계층

```
Layer 1: Gradle 모듈 의존성 (build.gradle.kts)
  → 모듈 간 의존 방향이 맞는가?
  → 금지된 라이브러리 의존이 있는가? (domain에 Spring 등)
  → 규칙 자체가 현실과 맞는가?

Layer 2: ArchUnit 코드 의존성
  → 패키지 간 격리가 지켜지는가?
  → 계층 접근 규칙이 지켜지는가?
  → 프레임워크 순수성이 지켜지는가?
```

Layer 1에서 위반이 있으면 Layer 2는 의미가 없다. 반드시 Layer 1부터 검증한다.

## 테스트 파일 위치

```
xxx-domain/src/test/kotlin/com/xxx/domain/ArchitectureTest.kt
xxx-infra/src/test/kotlin/com/xxx/infra/ArchitectureTest.kt
xxx-app-api/src/test/kotlin/com/xxx/api/ArchitectureTest.kt
```

각 모듈의 테스트 루트 패키지에 `ArchitectureTest.kt` 하나만 둔다.

## 기본 구조

```kotlin
package com.xxx.{모듈}

import com.tngtech.archunit.core.importer.ClassFileImporter
import com.tngtech.archunit.core.importer.ImportOption
import com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses
import org.junit.jupiter.api.Test

class ArchitectureTest {

    // MUST: DoNotIncludeTests — MockK 등 테스트 의존성 오탐 방지
    private val classes = ClassFileImporter()
        .withImportOption(ImportOption.DoNotIncludeTests())
        .importPackages("com.xxx.{모듈}")

    @Test
    fun `규칙을 한국어로 명확히 서술한다`() {
        noClasses()
            .that().resideInAPackage("...")
            .should().dependOnClassesThat().resideInAPackage("...")
            .because("한국어로 위반 이유 명시")
            .check(classes)
    }
}
```

## 규칙 카테고리

### 1. 모듈 경계 규칙 (의존성 방향)

multi-module.md의 의존성 방향을 강제한다.

```kotlin
// domain은 infra를 참조할 수 없다
noClasses()
    .that().resideInAPackage("com.xxx.domain..")
    .should().dependOnClassesThat().resideInAPackage("com.xxx.infra..")
    .because("domain → infra 의존은 아키텍처 위반")
    .check(classes)

// domain은 api를 참조할 수 없다
noClasses()
    .that().resideInAPackage("com.xxx.domain..")
    .should().dependOnClassesThat().resideInAPackage("com.xxx.api..")
    .because("domain → api 의존은 아키텍처 위반")
    .check(classes)

// infra는 api를 참조할 수 없다 (하위 → 상위)
noClasses()
    .that().resideInAPackage("com.xxx.infra..")
    .should().dependOnClassesThat().resideInAPackage("com.xxx.api..")
    .because("infra → api 의존은 아키텍처 위반 (하위 → 상위)")
    .check(classes)
```

### 2. 프레임워크 순수성 규칙 (domain 모듈)

domain 모듈이 순수 Kotlin을 유지하는지 검증한다.

```kotlin
// Spring 의존 금지
noClasses()
    .that().resideInAPackage("com.xxx.domain..")
    .should().dependOnClassesThat().resideInAPackage("org.springframework..")
    .because("domain 모듈은 순수 Kotlin이어야 한다 — Spring 의존 금지")
    .check(classes)

// JPA 의존 금지
noClasses()
    .that().resideInAPackage("com.xxx.domain..")
    .should().dependOnClassesThat().resideInAPackage("jakarta.persistence..")
    .because("domain 모듈은 순수 Kotlin이어야 한다 — JPA 의존 금지")
    .check(classes)
```

### 3. 패키지 격리 규칙 (infra 내부)

infra 모듈 내 인프라별 패키지가 서로 직접 참조하지 않도록 격리한다.

```kotlin
// notification ↛ kafka (인프라 세부사항 격리)
noClasses()
    .that().resideInAPackage("..notification..")
    .should().dependOnClassesThat().resideInAPackage("..kafka..")
    .because("notification은 인프라 구현 세부사항(kafka)에 의존하면 안 된다")
    .check(classes)

// kafka ↛ redis (독립 인프라 간 격리)
noClasses()
    .that().resideInAPackage("..kafka..")
    .should().dependOnClassesThat().resideInAPackage("..redis..")
    .because("kafka와 redis는 독립적인 인프라 구현이다")
    .check(classes)
```

### 4. 계층 접근 규칙 (app 모듈)

Controller가 domain service를 통해서만 접근하도록 강제한다.

```kotlin
// Controller ↛ infra (domain service 거쳐야 함)
noClasses()
    .that().resideInAPackage("..controller..")
    .should().dependOnClassesThat().resideInAPackage("com.xxx.infra..")
    .because("Controller는 domain service를 통해 접근해야 한다")
    .check(classes)

// DTO ↛ infra (JPA Entity 참조 금지)
noClasses()
    .that().resideInAPackage("..dto..")
    .should().dependOnClassesThat().resideInAPackage("com.xxx.infra..")
    .because("API DTO는 infra 계층에 의존하면 안 된다")
    .check(classes)
```

### 5. 서비스 순수성 규칙 (domain service)

domain service가 허용된 패키지만 참조하는지 검증한다.

```kotlin
noClasses()
    .that().resideInAPackage("..service..")
    .should().dependOnClassesThat()
    .resideOutsideOfPackages(
        "com.xxx.domain..",
        "com.xxx.common..",
        "java..",
        "kotlin..",
        "org.jetbrains..",
    )
    .because("domain service는 domain, common, JDK만 참조 가능")
    .check(classes)
```

## 새 규칙 추가 시점

| 변경 | 추가할 규칙 | 대상 모듈 |
|------|------------|----------|
| 새 모듈 추가 | 모듈 경계 규칙 (상위↛하위, 하위↛상위) | 양쪽 모듈 |
| infra에 새 인프라 패키지 추가 | 패키지 격리 규칙 (기존 패키지 ↛ 신규, 신규 ↛ 기존) | alarm-infra |
| 새 도메인 추가 | 도메인 간 격리 (필요 시) | alarm-domain |
| app 모듈에 새 계층 추가 | 계층 접근 규칙 | 해당 app 모듈 |

## 실행

```bash
# ArchitectureTest가 있는 모듈만 실행
./gradlew :alarm-domain:test :alarm-infra:test :alarm-api:test --tests '*ArchitectureTest*'
```

ArchitectureTest가 없는 모듈을 포함하면 "No tests found" 에러 발생.

## 안티패턴

```kotlin
// BAD: 테스트 클래스도 스캔됨 → MockK 등 오탐
private val classes = ClassFileImporter()
    .importPackages("com.xxx.domain")

// GOOD: 테스트 클래스 제외
private val classes = ClassFileImporter()
    .withImportOption(ImportOption.DoNotIncludeTests())
    .importPackages("com.xxx.domain")

// BAD: because 없음 → 위반 시 이유 불명
noClasses()
    .that().resideInAPackage("..controller..")
    .should().dependOnClassesThat().resideInAPackage("com.xxx.infra..")
    .check(classes)

// GOOD: because로 이유 명시
noClasses()
    .that().resideInAPackage("..controller..")
    .should().dependOnClassesThat().resideInAPackage("com.xxx.infra..")
    .because("Controller는 domain service를 통해 접근해야 한다")
    .check(classes)

// BAD: 너무 넓은 규칙 (모든 외부 참조 금지)
noClasses()
    .that().resideInAPackage("com.xxx.domain..")
    .should().onlyDependOnClassesThat().resideInAPackage("com.xxx.domain..")

// GOOD: 허용 패키지를 명시적으로 나열
noClasses()
    .that().resideInAPackage("..service..")
    .should().dependOnClassesThat()
    .resideOutsideOfPackages("com.xxx.domain..", "com.xxx.common..", "java..", "kotlin..", "org.jetbrains..")
```

## 의존성

```kotlin
// build.gradle.kts (각 모듈)
testImplementation(libs.archunit.junit5)
```

```toml
# gradle/libs.versions.toml
[versions]
archunit = "1.3.0"

[libraries]
archunit-junit5 = { module = "com.tngtech.archunit:archunit-junit5", version.ref = "archunit" }
```
