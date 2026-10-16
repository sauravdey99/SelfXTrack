package com.selfxtrack.app.ui

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection
import com.selfxtrack.app.i18n.I18n
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.selfxtrack.app.SelfXApp
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.LangReq
import com.selfxtrack.app.live.AlertService
import com.selfxtrack.app.live.PushService
import kotlinx.coroutines.launch
import org.osmdroid.config.Configuration


class MainActivity : ComponentActivity() {
    private val pendingSos = mutableStateOf<Int?>(null)
    private val pendingSchool = mutableStateOf<Int?>(null)   // school SOS id to open
    private val pendingHelp = mutableStateOf<Int?>(null)
    private var homeDecided = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val session = (application as SelfXApp).session
        Api.session = session
        Configuration.getInstance().apply {
            load(applicationContext, getSharedPreferences("osmdroid", MODE_PRIVATE))
            userAgentValue = "SelfXTrack/0.1 (${packageName})"   // tile servers require a real user agent
            osmdroidTileCache = java.io.File(cacheDir, "tiles")
        }
        if (Build.VERSION.SDK_INT >= 33)
            registerForActivityResult(ActivityResultContracts.RequestPermission()) {}
                .launch(Manifest.permission.POST_NOTIFICATIONS)
        PushService.init(applicationContext)
        if (session.token != null) PushService.registerToken(applicationContext)
        pendingSos.value = intent.getIntExtra(EXTRA_SOS_ID, -1).takeIf { it > 0 }
        pendingSchool.value = intent.getIntExtra(EXTRA_SCHOOL_SOS, -1).takeIf { it > 0 }
        pendingHelp.value = intent.getIntExtra(EXTRA_HELP_ID, -1).takeIf { it > 0 }

        setContent {
            // Urdu is right-to-left; every other app language is left-to-right.
            CompositionLocalProvider(LocalLayoutDirection provides if (I18n.rtl) LayoutDirection.Rtl else LayoutDirection.Ltr) {
            SelfXTheme {
                val nav = rememberNavController()
                val home = if (session.token == null) "auth" else "devices"
                // First start: ask app language + AI language once; later they are changed in Settings.
                val start = if (session.appLang == null) "lang" else home
                val scope = rememberCoroutineScope()
                LaunchedEffect(pendingSos.value) {
                    pendingSos.value?.let { nav.navigate("sos/$it"); pendingSos.value = null }
                }
                LaunchedEffect(pendingHelp.value) {
                    pendingHelp.value?.let { nav.navigate("help/$it"); pendingHelp.value = null }
                }
                LaunchedEffect(pendingSchool.value) {
                    // teacher tapped a student emergency -> open that child's live emergency screen
                    pendingSchool.value?.let { nav.navigate("staff-track/$it"); pendingSchool.value = null }
                }
                NavHost(nav, startDestination = start) {
                    composable("lang") {
                        LanguageSettingsScreen(session.appLang, session.aiLang, firstRun = true, onSave = { app, ai ->
                            scope.launch { session.setLanguages(app, ai) }
                            nav.navigate(home) { popUpTo("lang") { inclusive = true } }
                        })
                    }
                    composable("settings") {
                        LanguageSettingsScreen(session.appLang, session.aiLang, firstRun = false, onSave = { app, ai ->
                            scope.launch {
                                session.setLanguages(app, ai)
                                runCatching { Api.api.setLang(LangReq(app)) }   // alerts written by the server
                                nav.popBackStack()
                            }
                        }, onBack = { nav.popBackStack() })
                    }
                    composable("auth") {
                        AuthScreen(onLoggedIn = {
                            AlertService.start(this@MainActivity)
                            PushService.registerToken(applicationContext)
                            nav.navigate("devices") { popUpTo("auth") { inclusive = true } }
                            nav.navigate("verify")   // shows only if the phone is not verified yet
                        })
                    }
                    composable("verify") {
                        var checked by remember { mutableStateOf(false) }
                        LaunchedEffect(Unit) {
                            runCatching { Api.api.me() }.onSuccess { if (it.phone_verified) nav.popBackStack() else checked = true }
                                .onFailure { checked = true }
                        }
                        if (checked) VerifyPhoneScreen(onVerified = { nav.popBackStack() })
                    }
                    composable("contacts/{id}") { TeacherContactsScreen(it.arguments!!.getString("id")!!, onBack = { nav.popBackStack() }) }
                    composable("help/{id}") { HelpScreen(it.arguments!!.getString("id")!!.toInt(), onBack = { nav.popBackStack() }) }
                    composable("devices") {
                        LaunchedEffect(Unit) {
                            AlertService.start(this@MainActivity)
                            // keep the server's copy of the app language in sync (after login / reinstall)
                            runCatching { Api.api.setLang(LangReq(session.appLang ?: "en")) }
                            runCatching { Api.api.me() }.onSuccess { if (!it.phone_verified) nav.navigate("verify") }
                            // Teacher / staff with no tracker of their own -> School dashboard is the home screen
                            if (!homeDecided) {
                                homeDecided = true
                                val mine = runCatching { Api.api.devices() }.getOrNull()
                                val board = runCatching { Api.api.staffBoard() }.getOrNull()
                                if (mine != null && mine.isEmpty() && board != null && board.children.isNotEmpty())
                                    nav.navigate("school-home") { popUpTo("devices") { inclusive = true } }
                            }
                        }
                        DevicesScreen(
                            onAsk = { nav.navigate("ask/$it") },
                            onSetup = { nav.navigate("setup/$it") },
                            onPlans = { nav.navigate("plans") },
                            onOpen = { nav.navigate("map/$it") },
                            onAdd = { nav.navigate("add") },
                            onSos = { nav.navigate("sos/$it") },
                            onSchools = { nav.navigate("schools") },
                            onSettings = { nav.navigate("settings") },
                            onLogout = {
                                AlertService.stop(this@MainActivity)
                                nav.navigate("auth") { popUpTo(0) }
                            })
                    }
                    composable("add") { AddDeviceScreen(onBack = { nav.popBackStack() }, onDone = { d -> nav.navigate("setup-new/$d") { popUpTo("devices") } }) }
                    listOf("setup", "setup-new").forEach { r ->
                        composable("$r/{id}") {
                            ChildSetupScreen(it.arguments!!.getString("id")!!, isNew = r == "setup-new",
                                onBack = { nav.popBackStack() },
                                onZones = { d -> nav.navigate("zones/$d") }, onContacts = { d -> nav.navigate("contacts/$d") },
                                onPlace = { d, pid -> nav.navigate("place/$d/$pid") })
                        }
                    }
                    composable("map/{id}") { MapScreen(it.arguments!!.getString("id")!!, onBack = { nav.popBackStack() },
                        onSos = { s -> nav.navigate("sos/$s") }, onZones = { d -> nav.navigate("zones/$d") },
                        onSetup = { d -> nav.navigate("setup/$d") },
                        onInsights = { d -> nav.navigate("insights/$d") }) }
                    composable("insights/{id}") {
                        val id = it.arguments!!.getString("id")!!
                        InsightsScreen(id, null, onBack = { nav.popBackStack() }, onPlans = { nav.navigate("plans") },
                            onDay = { d -> nav.navigate("day/$id/$d") }, onAsk = { nav.navigate("ask/$id") })
                    }
                    composable("day/{id}/{date}") {
                        DayDetailScreen(it.arguments!!.getString("id")!!, it.arguments!!.getString("date")!!, onBack = { nav.popBackStack() })
                    }
                    composable("ask/{id}") { AskScreen(it.arguments!!.getString("id")!!, appLang(session.aiLang),
                        onBack = { nav.popBackStack() }, onLanguage = { nav.navigate("settings") }) }
                    composable("plans") { PlansScreen(onBack = { nav.popBackStack() }) }
                    // all places of a child (was "Safe zones"); place/{id}/0 = new place
                    composable("zones/{id}") {
                        val id = it.arguments!!.getString("id")!!
                        PlacesListScreen(id, onBack = { nav.popBackStack() }, onEdit = { pid -> nav.navigate("place/$id/$pid") })
                    }
                    composable("place/{id}/{pid}") {
                        PlaceEditorScreen(it.arguments!!.getString("id")!!, it.arguments!!.getString("pid")!!.toIntOrNull() ?: 0,
                            onDone = { nav.popBackStack() })
                    }
                    composable("schools") { StaffBoardScreen(onBack = { nav.popBackStack() }, onVerify = { nav.navigate("verify") },
                        onTrack = { s -> nav.navigate("staff-track/$s") }) }
                    composable("school-home") {
                        val scope = androidx.compose.runtime.rememberCoroutineScope()
                        LaunchedEffect(Unit) { runCatching { Api.api.setLang(LangReq(session.appLang ?: "en")) } }
                        StaffBoardScreen(onBack = {}, onVerify = { nav.navigate("verify") }, onTrack = { s -> nav.navigate("staff-track/$s") },
                            isHome = true, onFamily = { nav.navigate("devices") }, onSettings = { nav.navigate("settings") },
                            onPlans = { nav.navigate("plans") },
                            onLogout = { scope.launch {
                                runCatching { Api.api.logout() }; session.logout()
                                AlertService.stop(this@MainActivity); nav.navigate("auth") { popUpTo(0) }
                            } })
                    }
                    composable("staff-track/{id}") { StaffTrackScreen(it.arguments!!.getString("id")!!.toInt(), onBack = { nav.popBackStack() }) }
                    composable("school-sos/{id}") { SchoolSosScreen(it.arguments!!.getString("id")!!.toInt(), onBack = { nav.popBackStack() }) }
                    composable("sos/{id}") { SosScreen(it.arguments!!.getString("id")!!.toInt(), onBack = { nav.popBackStack() }) }
                }
            }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.getIntExtra(EXTRA_SOS_ID, -1).takeIf { it > 0 }?.let { pendingSos.value = it }
        intent.getIntExtra(EXTRA_SCHOOL_SOS, -1).takeIf { it > 0 }?.let { pendingSchool.value = it }
        intent.getIntExtra(EXTRA_HELP_ID, -1).takeIf { it > 0 }?.let { pendingHelp.value = it }
    }

    companion object {
        const val EXTRA_SOS_ID = "sos_id"
        const val EXTRA_SCHOOL_SOS = "school_sos_id"
        const val EXTRA_HELP_ID = "help_id"
    }
}
