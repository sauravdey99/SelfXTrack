import java.util.Properties

// Optional Firebase push config (see README "Push notifications"). Missing file = push disabled.
val fb = Properties().apply { rootProject.file("firebase.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) } }
fun fbv(k: String) = "\"" + (fb.getProperty(k) ?: "") + "\""

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.selfxtrack.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.selfxtrack.app"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
        // Emulator -> your computer's backend. Change to your server URL for real phones.
        buildConfigField("String", "DEFAULT_SERVER", "\"http://10.0.2.2:8000\"")
        buildConfigField("String", "FB_API_KEY", fbv("apiKey"))
        buildConfigField("String", "FB_APP_ID", fbv("appId"))
        buildConfigField("String", "FB_PROJECT_ID", fbv("projectId"))
        buildConfigField("String", "FB_SENDER_ID", fbv("senderId"))
    }
    buildTypes {
        // Release talks to the real server over HTTPS only (see src/main/res/xml/network_security_config.xml).
        // Set your domain here before publishing.
        release { buildConfigField("String", "DEFAULT_SERVER", "\"https://api.selfxtrack.in\"") }
    }
    buildFeatures { compose = true; buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.09.02")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.navigation:navigation-compose:2.8.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.6")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.6")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.datastore:datastore-preferences:1.1.1")
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-gson:2.11.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("org.osmdroid:osmdroid-android:6.1.20")   // OpenStreetMap, no API key needed
    implementation("com.google.firebase:firebase-messaging:24.0.1")
    implementation("com.google.android.gms:play-services-location:21.3.0")
}
