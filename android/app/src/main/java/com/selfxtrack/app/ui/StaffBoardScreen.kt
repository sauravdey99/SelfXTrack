package com.selfxtrack.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.ChildCare
import androidx.compose.material.icons.filled.Elderly
import androidx.compose.material.icons.filled.FamilyRestroom
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.BoardChild
import com.selfxtrack.app.data.userMessage
import com.selfxtrack.app.i18n.t
import com.selfxtrack.app.live.LiveEvents
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * School dashboard for teachers / staff. A child appears here when the parent added this phone number
 * in Child setup → School. Children in SOS are shown first with live info; others show name + class only.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StaffBoardScreen(onBack: () -> Unit, onVerify: () -> Unit, onTrack: (Int) -> Unit,
                     isHome: Boolean = false, onFamily: () -> Unit = {}, onSettings: () -> Unit = {}, onLogout: () -> Unit = {},
                     onPlans: () -> Unit = {}) {
    var confirmLogout by remember { mutableStateOf(false) }
    if (confirmLogout) AlertDialog(onDismissRequest = { confirmLogout = false }, title = { Text(t("Log out?")) },
        text = { Text(t("You will NOT receive student emergency alerts on this phone until you log in again.")) },
        confirmButton = { TextButton(onClick = { confirmLogout = false; onLogout() }) { Text(t("Log out"), color = MaterialTheme.colorScheme.error) } },
        dismissButton = { TextButton(onClick = { confirmLogout = false }) { Text(t("Cancel")) } })
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var verified by remember { mutableStateOf(true) }
    var list by remember { mutableStateOf<List<BoardChild>>(emptyList()) }
    var msg by remember { mutableStateOf<String?>(null) }
    var ackFor by remember { mutableStateOf<Pair<Int, String>?>(null) }

    suspend fun load() {
        runCatching { Api.api.staffBoard() }.onSuccess { verified = it.verified; list = it.children; msg = null }.onFailure { msg = it.userMessage() }
    }
    ackFor?.let { (id, nm) ->
        ConfirmDialog(t("I'm on it?"), t("The family will see that you (school) are handling {0}'s SOS. Only confirm if you are going to help now.", nm),
            t("Confirm"), onConfirm = {
                ackFor = null
                scope.launch { runCatching { Api.api.staffAck(id) }; load() }
            }, onCancel = { ackFor = null })
    }
    LaunchedEffect(Unit) { while (true) { load(); delay(20_000) } }
    LaunchedEffect(Unit) { LiveEvents.events.collect { load() } }

    // same side menu as the family page (when this dashboard is the teacher's home screen)
    var helperOn by remember { mutableStateOf(true) }
    var showAccount by remember { mutableStateOf(false) }
    var showHelper by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { if (isHome) runCatching { Api.api.me() }.onSuccess { helperOn = it.helper_available } }
    if (showAccount) AccountDialog(onClose = { showAccount = false }, onDeleted = { showAccount = false; onLogout() })
    if (showHelper) AlertDialog(onDismissRequest = { showHelper = false }, title = { Text(t("Help children nearby")) },
        text = { Text(t("When a family nearby presses “Emergency – Group”, you get an alert. Your approximate location is used only to find you; families see your name and position only if you tap “I can help”.")) },
        confirmButton = { TextButton(onClick = { showHelper = false }) { Text(t("Done")) } })
    val drawer = rememberDrawerState(DrawerValue.Closed)
    fun go(action: () -> Unit) { scope.launch { drawer.close() }; action() }

    ModalNavigationDrawer(drawerState = drawer, gesturesEnabled = isHome, drawerContent = {
        if (isHome) AppMenu(helperOn = helperOn,
            onHelper = { on -> helperOn = on
                scope.launch { runCatching { Api.api.setAvailability(com.selfxtrack.app.data.Availability(on)) } } },
            onHelperInfo = { go { showHelper = true } }, onPlans = { go(onPlans) }, onSchools = { go(onFamily) },
            onSettings = { go(onSettings) }, onAccount = { go { showAccount = true } }, onLogout = { go { confirmLogout = true } },
            schoolHome = true)
    }) {
    Scaffold(topBar = {
        TopAppBar(title = { Text(t("Children I look after"), fontWeight = androidx.compose.ui.text.font.FontWeight.Bold) },
            navigationIcon = {
                if (isHome) IconButton(onClick = { scope.launch { drawer.open() } }) {
                    Icon(androidx.compose.material.icons.Icons.Default.Menu, t("Menu"))
                } else IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) }
            })
    }) { pad ->
        LazyColumn(Modifier.padding(pad).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (!verified) item {
                Text(t("Verify your mobile number to see the students whose parents added you as teacher / staff."))
                Button(onClick = onVerify) { Text(t("Verify phone")) }
            } else if (list.isEmpty()) item {
                Text(t("No children yet. When a parent adds your mobile number to a place in Child setup (school, tuition, swimming …), the child appears here and you get their emergency alerts."), color = Color.Gray)
            }
            msg?.let { item { Text(it, color = MaterialTheme.colorScheme.secondary) } }
            val sosCount = list.count { it.sos != null }
            if (verified) item {
                // same friendly header as the family page
                val first = Api.session.name?.split(" ")?.firstOrNull()?.takeIf { it.isNotBlank() }
                Column(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 8.dp)) {
                    Text(if (first != null) t("Hi {0} 👋", first) else t("Hi 👋"), style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold)
                    if (list.isNotEmpty()) Text(if (sosCount > 0) t("🚨 {0} SOS active – tap the red card", sosCount)
                        else t("✅ No active SOS · {0} children", list.size),
                        color = if (sosCount > 0) Color(0xFFC62828) else Color.Gray)
                }
            }
            items(list, key = { it.device_id }) { c ->
                val s = c.sos
                val accent = if (s != null) Color(0xFFC62828) else placeColor(c.place_kind ?: "school")
                ElevatedCard(Modifier.fillMaxWidth(), colors = CardDefaults.elevatedCardColors(
                    containerColor = if (s != null) Color(0xFFFFEBEE) else Color.White)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                            Box {
                                Box(Modifier.size(52.dp).clip(CircleShape).background(accent.copy(alpha = 0.12f)),
                                    contentAlignment = androidx.compose.ui.Alignment.Center) {
                                    Icon(if (c.kind == "elderly") Icons.Default.Elderly else Icons.Default.ChildCare, null,
                                        Modifier.size(30.dp), tint = if (s != null) accent else MaterialTheme.colorScheme.primary)
                                }
                                if (s != null) Box(Modifier.size(14.dp).align(androidx.compose.ui.Alignment.BottomEnd).clip(CircleShape)
                                    .background(Color.White).padding(2.dp).clip(CircleShape).background(accent))
                            }
                            Spacer(Modifier.width(14.dp))
                            Column(Modifier.weight(1f)) {
                                Text(c.name, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                                Text(placeEmoji(c.place_kind ?: "school") + " " + (c.school ?: placeKindLabel(c.place_kind ?: "school")) +
                                    (c.class_name?.let { " · " + t("Class {0}", it) } ?: ""),
                                    color = Color.Gray, style = MaterialTheme.typography.bodyMedium)
                            }
                            Surface(shape = RoundedCornerShape(12.dp), color = accent.copy(alpha = 0.12f)) {
                                Text(t("you: {0}", personRoleLabel(c.my_role)), Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                    style = MaterialTheme.typography.labelMedium, color = accent)
                            }
                        }
                        if (s != null) Text(t("🚨 SOS ACTIVE – tap now"), color = accent, fontWeight = FontWeight.Bold)
                        if (s != null) {
                            Text("SOS ${ago(s.started_at)} · ${if (s.status == "active") t("waiting for response") else t("someone is responding")}")
                            Text(t("Last update {0} · battery {1}%", ago(s.last_seen), s.battery ?: "–") +
                                (s.speed_kmh?.let { " · " + t("{0} km/h", it.toInt()) } ?: ""))
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Button(onClick = { ctx.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:112"))) },
                                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFC62828))) { Text(t("Call 112")) }
                                OutlinedButton(enabled = s.lat != null, onClick = {
                                    ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("google.navigation:q=${s.lat},${s.lon}")))
                                }) { Text(t("Navigate")) }
                                if (s.status == "active") OutlinedButton(onClick = { ackFor = s.sos_id to c.name }) { Text(t("I'm on it")) }
                            }
                            Button(onClick = { onTrack(s.sos_id) }, modifier = Modifier.fillMaxWidth()) { Text(t("📍 Track live")) }
                        }
                        if (s != null) c.parents.filter { it.phone != null }.forEach { p ->
                            val who = if (p.role == "owner") t("parent") else t("family")
                            if (p.raised) Button(onClick = { ctx.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:${p.phone}"))) },
                                modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2E7D32))) {
                                Text(t("📞 Call {0} – raised this alert", p.name ?: t("parent")))
                            } else OutlinedButton(onClick = { ctx.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:${p.phone}"))) },
                                modifier = Modifier.fillMaxWidth()) {
                                Text(t("📞 Call {0} ({1})", p.name ?: who, who))
                            }
                        }
                        if (s == null) Text(t("No active alert – parent contacts and location are shown only during an SOS."),
                            color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                        if (s != null) {
                            Text(t("Do not confront anyone. Observe, inform the family and police."), color = Color.Gray)
                        }
                    }
                }
            }
        }
    }
    }
}
