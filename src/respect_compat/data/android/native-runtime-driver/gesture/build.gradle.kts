// SPDX-FileCopyrightText: 2026 Jim Plamondon
// SPDX-License-Identifier: Apache-2.0

plugins {
    id("com.android.application")
}

android {
    namespace = "org.respect.testkit.gesture"
    compileSdk = 36

    defaultConfig {
        applicationId = "org.respect.testkit.gesture"
        minSdk = 27
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
