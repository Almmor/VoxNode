// VoxNode 手机遥控 App —— 顶层构建脚本
// 版本组合刻意与常见本地缓存对齐（AGP 8.2.2 / Kotlin 1.9.20 / Gradle 8.2+），
// 在无外网的环境下也能直接构建。
plugins {
    id("com.android.application") version "8.2.2" apply false
    id("org.jetbrains.kotlin.android") version "1.9.20" apply false
}
