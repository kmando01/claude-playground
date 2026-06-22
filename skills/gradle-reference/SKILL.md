---
name: gradle-reference
description: Gradle 멀티모듈 빌드 템플릿 레퍼런스. settings.gradle.kts, libs.versions.toml, 모듈별 build.gradle.kts 전체 템플릿 포함. 새 모듈 추가, 빌드 설정, 의존성 구성 시 참조.
---

# Gradle 멀티모듈 레퍼런스

## 프로젝트 구조

```
project-root/
├── settings.gradle.kts
├── build.gradle.kts                  # 루트 (공통 설정)
├── gradle/
│   └── libs.versions.toml            # 의존성 버전 카탈로그
├── xxx-app-api/
│   └── build.gradle.kts
├── xxx-app-admin/
│   └── build.gradle.kts
├── xxx-app-batch/
│   └── build.gradle.kts
├── xxx-domain/
│   └── build.gradle.kts
├── xxx-infra/
│   └── build.gradle.kts
├── xxx-client-external/
│   └── build.gradle.kts
└── xxx-common/
    └── build.gradle.kts
```

## settings.gradle.kts

```kotlin
rootProject.name = "xxx"

include(
    "xxx-app-api",
    "xxx-app-admin",
    "xxx-app-batch",
    "xxx-domain",
    "xxx-infra",
    "xxx-client-external",
    "xxx-common",
)

dependencyResolutionManagement {
    versionCatalogs {
        create("libs") {
            from(files("gradle/libs.versions.toml"))
        }
    }
}
```

## gradle/libs.versions.toml

```toml
[versions]
spring-boot = "3.3.0"
kotlin = "1.9.24"
spring-dependency-management = "1.1.5"

# test
mockk = "1.13.10"
testcontainers = "1.19.7"
restdocs-api-spec = "0.19.2"

# infra
spring-cloud = "2023.0.1"

[libraries]
# Spring
spring-boot-starter-web = { module = "org.springframework.boot:spring-boot-starter-web" }
spring-boot-starter-data-jpa = { module = "org.springframework.boot:spring-boot-starter-data-jpa" }
spring-boot-starter-data-redis = { module = "org.springframework.boot:spring-boot-starter-data-redis" }
spring-boot-starter-validation = { module = "org.springframework.boot:spring-boot-starter-validation" }
spring-boot-starter-actuator = { module = "org.springframework.boot:spring-boot-starter-actuator" }
spring-boot-starter-security = { module = "org.springframework.boot:spring-boot-starter-security" }
spring-boot-starter-batch = { module = "org.springframework.boot:spring-boot-starter-batch" }

# Kotlin
jackson-module-kotlin = { module = "com.fasterxml.jackson.module:jackson-module-kotlin" }
kotlin-reflect = { module = "org.jetbrains.kotlin:kotlin-reflect" }

# Database
mysql-connector = { module = "com.mysql:mysql-connector-j" }
h2-database = { module = "com.h2database:h2" }

# Monitoring
micrometer-registry-prometheus = { module = "io.micrometer:micrometer-registry-prometheus" }

# Test
spring-boot-starter-test = { module = "org.springframework.boot:spring-boot-starter-test" }
spring-restdocs-mockmvc = { module = "org.springframework.restdocs:spring-restdocs-mockmvc" }
restdocs-api-spec-mockmvc = { module = "com.epages:restdocs-api-spec-mockmvc", version.ref = "restdocs-api-spec" }
mockk = { module = "io.mockk:mockk", version.ref = "mockk" }
spring-mockk = { module = "com.ninja-squad:springmockk", version = "4.0.2" }
testcontainers-bom = { module = "org.testcontainers:testcontainers-bom", version.ref = "testcontainers" }
testcontainers-junit = { module = "org.testcontainers:junit-jupiter" }
testcontainers-mysql = { module = "org.testcontainers:mysql" }
testcontainers-kafka = { module = "org.testcontainers:kafka" }

# Kafka
spring-kafka = { module = "org.springframework.kafka:spring-kafka" }
spring-kafka-test = { module = "org.springframework.kafka:spring-kafka-test" }

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
spring-dependency-management = { id = "io.spring.dependency-management", version.ref = "spring-dependency-management" }
kotlin-jvm = { id = "org.jetbrains.kotlin.jvm", version.ref = "kotlin" }
kotlin-spring = { id = "org.jetbrains.kotlin.plugin.spring", version.ref = "kotlin" }
kotlin-jpa = { id = "org.jetbrains.kotlin.plugin.jpa", version.ref = "kotlin" }
restdocs-api-spec = { id = "com.epages.restdocs-api-spec", version.ref = "restdocs-api-spec" }
```

## 루트 build.gradle.kts

```kotlin
plugins {
    alias(libs.plugins.spring.boot) apply false
    alias(libs.plugins.spring.dependency.management) apply false
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.spring) apply false
    alias(libs.plugins.kotlin.jpa) apply false
}

allprojects {
    group = "com.xxx"
    version = "0.0.1-SNAPSHOT"

    repositories {
        mavenCentral()
    }
}

subprojects {
    apply(plugin = "org.jetbrains.kotlin.jvm")
    apply(plugin = "io.spring.dependency-management")

    dependencies {
        "implementation"(libs.kotlin.reflect)
        "implementation"(libs.jackson.module.kotlin)
        "testImplementation"(libs.spring.boot.starter.test)
        "testImplementation"(libs.mockk)
    }

    the<io.spring.gradle.dependencymanagement.DependencyManagementExtension>().apply {
        imports {
            mavenBom(libs.testcontainers.bom.get().toString())
        }
    }

    tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile> {
        kotlinOptions {
            freeCompilerArgs = listOf("-Xjsr305=strict")
            jvmTarget = "17"
        }
    }

    tasks.withType<Test> {
        useJUnitPlatform()
    }
}
```

## 모듈별 build.gradle.kts

### xxx-common
```kotlin
// 의존성 없음 - 순수 Kotlin
dependencies {
    // 필요 시 유틸리티 라이브러리만
}
```

### xxx-domain
```kotlin
dependencies {
    implementation(project(":xxx-common"))
    // 순수 Kotlin만! Spring/JPA 의존성 절대 금지
    testImplementation(libs.spring.boot.starter.test)
    testImplementation(libs.mockk)
}
```

### xxx-infra
```kotlin
apply(plugin = "org.jetbrains.kotlin.plugin.spring")
apply(plugin = "org.jetbrains.kotlin.plugin.jpa")
apply(plugin = "org.springframework.boot")

tasks.bootJar { enabled = false }
tasks.jar { enabled = true }

dependencies {
    implementation(project(":xxx-domain"))
    implementation(project(":xxx-common"))
    implementation(libs.spring.boot.starter.data.jpa)
    runtimeOnly(libs.mysql.connector)
    implementation(libs.spring.boot.starter.data.redis)
    implementation(libs.spring.kafka)
    testImplementation(libs.testcontainers.junit)
    testImplementation(libs.testcontainers.mysql)
    testRuntimeOnly(libs.h2.database)
}

allOpen {
    annotation("jakarta.persistence.Entity")
    annotation("jakarta.persistence.MappedSuperclass")
    annotation("jakarta.persistence.Embeddable")
}
```

### xxx-client-external
```kotlin
apply(plugin = "org.jetbrains.kotlin.plugin.spring")
apply(plugin = "org.springframework.boot")

tasks.bootJar { enabled = false }
tasks.jar { enabled = true }

dependencies {
    implementation(project(":xxx-common"))
    implementation(libs.spring.boot.starter.web)
    testImplementation("org.wiremock:wiremock-standalone:3.5.4")
}
```

### xxx-app-api
```kotlin
apply(plugin = "org.jetbrains.kotlin.plugin.spring")
apply(plugin = "org.springframework.boot")
apply(plugin = "com.epages.restdocs-api-spec")

dependencies {
    implementation(project(":xxx-domain"))
    implementation(project(":xxx-infra"))
    implementation(project(":xxx-client-external"))
    implementation(project(":xxx-common"))
    implementation(libs.spring.boot.starter.web)
    implementation(libs.spring.boot.starter.validation)
    implementation(libs.spring.boot.starter.actuator)
    implementation(libs.micrometer.registry.prometheus)
    testImplementation(libs.spring.restdocs.mockmvc)
    testImplementation(libs.restdocs.api.spec.mockmvc)
    testImplementation(libs.spring.mockk)
}

openapi3 {
    setServer("http://localhost:8080")
    title = "XXX API"
    description = "XXX 서비스 API"
    version = "1.0.0"
    format = "json"
    outputDirectory = "build/api-spec"
}
```

### xxx-app-admin
```kotlin
apply(plugin = "org.jetbrains.kotlin.plugin.spring")
apply(plugin = "org.springframework.boot")

dependencies {
    implementation(project(":xxx-domain"))
    implementation(project(":xxx-infra"))
    implementation(project(":xxx-common"))
    implementation(libs.spring.boot.starter.web)
    implementation(libs.spring.boot.starter.validation)
    implementation(libs.spring.boot.starter.security)
}
```

### xxx-app-batch
```kotlin
apply(plugin = "org.jetbrains.kotlin.plugin.spring")
apply(plugin = "org.springframework.boot")

dependencies {
    implementation(project(":xxx-domain"))
    implementation(project(":xxx-infra"))
    implementation(project(":xxx-common"))
    implementation(libs.spring.boot.starter.batch)
    implementation(libs.spring.kafka)
    testImplementation(libs.spring.kafka.test)
    testImplementation(libs.testcontainers.kafka)
}
```

## 의존성 scope 가이드

```kotlin
// implementation: 내부에서만 사용, 의존 모듈에 전파 안됨
implementation(libs.spring.boot.starter.data.jpa)

// api: 의존 모듈에도 전파됨 (가능하면 피하기)
api(project(":xxx-common"))

// runtimeOnly: 컴파일에 불필요, 런타임에만 필요
runtimeOnly(libs.mysql.connector)

// testImplementation: 테스트에서만
testImplementation(libs.mockk)
```

## 빌드 명령어

```bash
./gradlew build                          # 전체 빌드
./gradlew :xxx-domain:build              # 특정 모듈
./gradlew :xxx-app-api:dependencies      # 의존성 트리
./gradlew test                           # 전체 테스트
./gradlew :xxx-app-api:openapi3          # API 문서 생성
```
