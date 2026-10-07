plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.voxnode.remote"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.voxnode.remote"
        minSdk = 24
        targetSdk = 34
        versionCode = 600
        versionName = "0.6.0"
        resourceConfigurations += listOf("zh", "en")
    }

    signingConfigs {
        create("release") {
            // 仓库内附带的测试用签名（口令公开，仅用于本开源项目分发）
            storeFile = file("../keystore/voxnode.jks")
            storePassword = "voxnode"
            keyAlias = "voxnode"
            keyPassword = "voxnode"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false          // 保持稳定，不做混淆
            isShrinkResources = false
            signingConfig = signingConfigs.getByName("release")
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
        debug {
            applicationIdSuffix = ".debug"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    packaging {
        resources.excludes += setOf("META-INF/*.kotlin_module")
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("com.google.android.material:material:1.11.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
}
