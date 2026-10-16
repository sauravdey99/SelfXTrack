package com.selfxtrack.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.Device
import com.selfxtrack.app.data.DeleteReq
import com.selfxtrack.app.data.userMessage
import com.selfxtrack.app.i18n.t
import com.selfxtrack.app.live.LiveEvents
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DevicesScreen(onAsk: (String) -> Unit, onPlans: () -> Unit, onSetup: (String) -> Unit, onOpen: (String) -> Unit, onAdd: () -> Unit, onSos: (Int) -> Unit, onSchools: () -> Unit, onSettings: () -> Unit, onLogout: () -> Unit) {
    var devices by remember { mutableStateOf<List<Device>>(emptyList()) }
    var briefs by remember { mutableStateOf<Map<String, com.selfxtrack.app.data.Brief>>(emptyMap()) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    var confirmLogout by remember { mutableStateOf(false) }
    var showAccount by remember { mutableStateOf(false) }
    if (showAccount) AccountDialog(onClose = { showAccount = false }, onDeleted = { showAccount = false; onLogout() })
    var showHelper by remember { mutableStateOf(false) }
    var helperOn by remember { mutableStateOf(true) }
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val locPerm = androidx.activity.compose.rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.RequestMultiplePermissions()) {
        scope.launch { com.selfxtrack.app.live.HelperLocation.upload(ctx) }
    }
    LaunchedEffect(Unit) {
        runCatching { Api.api.me() }.onSuccess { helperOn = it.helper_available }
        if (!com.selfxtrack.app.live.HelperLocation.hasPermission(ctx))
            locPerm.launch(arrayOf(android.Manifest.permission.ACCESS_FINE_LOCATION, android.Manifest.permission.ACCESS_COARSE_LOCATION))
        else com.selfxtrack.app.live.HelperLocation.upload(ctx)
    }
    if (showHelper) {
        AlertDialog(onDismissRequest = { showHelper = false }, title = { Text(t("Help children nearby")) },
            text = {
                Column {
                    Text(t("When a family nearby presses “Emergency – Group”, you get an alert. Your approximate location is used only to find you; families see your name and position only if you tap “I can help”."))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(t("Available to help"), Modifier.weight(1f))
                        Switch(helperOn, { on ->
                            helperOn = on
                            scope.launch { runCatching { Api.api.setAvailability(com.selfxtrack.app.data.Availability(on)) } }
                        })
                    }
                }
            }, confirmButton = { TextButton(onClick = { showHelper = false }) { Text(t("Done")) } })
    }

    if (confirmLogout) {
        AlertDialog(
            onDismissRequest = { confirmLogout = false },
            icon = { Icon(Icons.Default.Logout, null) },
            title = { Text(t("Log out?")) },
            text = { Text(t("Do you want to log out? You will NOT receive SOS or safety alerts on this phone until you log in again.")) },
            confirmButton = {
                TextButton(onClick = {
                    confirmLogout = false
                    scope.launch { runCatching { Api.api.logout() }; Api.session.logout(); onLogout() }
                }) { Text(t("Log out"), color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = { TextButton(onClick = { confirmLogout = false }) { Text(t("Cancel")) } }
        )
    }

    suspend fun load() {
        runCatching { Api.api.devices() }.onSuccess { devices = it; error = null }.onFailure { error = it.userMessage() }
        runCatching { Api.api.familyBrief() }.onSuccess { l -> briefs = l.associateBy { it.device_id } }
    }
    LaunchedEffect(Unit) { while (true) { load(); delay(30_000) } }
    LaunchedEffect(Unit) { LiveEvents.events.collect { load() } }   // refresh on any live event

    val drawer = rememberDrawerState(DrawerValue.Closed)
    fun go(action: () -> Unit) { scope.launch { drawer.close() }; action() }
    ModalNavigationDrawer(drawerState = drawer, drawerContent = {
        AppMenu(helperOn = helperOn,
            onHelper = { on -> helperOn = on
                scope.launch { runCatching { Api.api.setAvailability(com.selfxtrack.app.data.Availability(on)) } } },
            onHelperInfo = { go { showHelper = true } }, onPlans = { go(onPlans) }, onSchools = { go(onSchools) },
            onSettings = { go(onSettings) }, onAccount = { go { showAccount = true } }, onLogout = { go { confirmLogout = true } })
    }) {
    Scaffold(
        topBar = {
            TopAppBar(title = { Text(t("My family"), fontWeight = FontWeight.Bold) },
                navigationIcon = { IconButton(onClick = { scope.launch { drawer.open() } }) { Icon(Icons.Default.Menu, t("Menu")) } })
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(onClick = onAdd, icon = { Icon(Icons.Default.Add, null) }, text = { Text(t("Add tracker")) })
        }
    ) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(16.dp)) }
            LazyColumn(contentPadding = PaddingValues(start = 12.dp, end = 12.dp, top = 4.dp, bottom = 96.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item { FamilyHeader(devices) }
                if (devices.isEmpty() && error == null) item {
                    Text(t("No trackers yet. Tap \"Add tracker\" and enter the code from the box."), Modifier.padding(12.dp))
                }
                items(devices, key = { it.device_id }) { d -> DeviceCard(d, briefs[d.device_id], onOpen, onSos, onSetup, onAsk) }
            }
        }
    }
    }
}

/** "Hi saurav 👋 · 2 trackers · 1 online" – a friendly summary at the top of the family page. */
@Composable
private fun FamilyHeader(devices: List<Device>) {
    val name = Api.session.name?.split(" ")?.firstOrNull()?.takeIf { it.isNotBlank() }
    val sos = devices.count { it.active_sos != null }
    Column(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 8.dp)) {
        Text(if (name != null) t("Hi {0} 👋", name) else t("Hi 👋"), style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold)
        if (devices.isNotEmpty()) Text(
            if (sos > 0) t("🚨 {0} SOS active – tap the red card", sos)
            else t("{0} trackers · {1} online", devices.size, devices.count { it.online }),
            color = if (sos > 0) Color(0xFFC62828) else Color.Gray)
    }
}

/** Side menu, same for everyone: every option with a title and one line saying what it does.
 *  schoolHome = shown on a teacher's school dashboard -> the switch item goes to "My own family". */
@Composable
internal fun AppMenu(helperOn: Boolean, onHelper: (Boolean) -> Unit, onHelperInfo: () -> Unit, onPlans: () -> Unit,
                     onSchools: () -> Unit, onSettings: () -> Unit, onAccount: () -> Unit, onLogout: () -> Unit,
                     schoolHome: Boolean = false) {
    ModalDrawerSheet(Modifier.widthIn(max = 320.dp)) {
        Column(Modifier.fillMaxHeight().verticalScroll(rememberScrollState())) {
            // header
            Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.primary).padding(20.dp)) {
                Box(Modifier.size(52.dp).clip(CircleShape).background(Color.White), contentAlignment = Alignment.Center) {
                    Icon(Icons.Default.Shield, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(30.dp))
                }
                Spacer(Modifier.height(10.dp))
                Text("SelfXTrack", color = Color.White, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Api.session.name?.let { Text(it, color = Color.White.copy(alpha = 0.85f)) }
            }
            Spacer(Modifier.height(8.dp))
            MenuItem(Icons.Default.WorkspacePremium, t("Plans"), t("Your plan and upgrades"), onPlans)
            if (schoolHome) MenuItem(Icons.Default.FamilyRestroom, t("My own family"), t("Your children's trackers"), onSchools)
            else MenuItem(Icons.Default.School, t("Children I look after"), t("For teachers, coaches, tutors and caretakers"), onSchools)
            // help nearby: switch right in the menu
            NavigationDrawerItem(
                icon = { Icon(Icons.Default.VolunteerActivism, null, tint = if (helperOn) Color(0xFF6A1B9A) else Color.Gray) },
                label = {
                    Column(Modifier.padding(vertical = 6.dp)) {
                        Text(t("Help nearby"), fontWeight = FontWeight.SemiBold)
                        Text(t("Get alerts when a child nearby needs help"), style = MaterialTheme.typography.bodySmall, color = Color.Gray)
                    }
                },
                badge = { Switch(helperOn, onHelper) },
                selected = false, onClick = onHelperInfo, modifier = Modifier.padding(horizontal = 12.dp))
            MenuItem(Icons.Default.Settings, t("Settings"), t("App language and AI language"), onSettings)
            MenuItem(Icons.Default.AccountCircle, t("Account & privacy"), t("Export or delete your data"), onAccount)
            HorizontalDivider(Modifier.padding(horizontal = 24.dp, vertical = 8.dp))
            NavigationDrawerItem(
                icon = { Icon(Icons.Default.Logout, null, tint = MaterialTheme.colorScheme.error) },
                label = { Text(t("Log out"), color = MaterialTheme.colorScheme.error, fontWeight = FontWeight.SemiBold) },
                selected = false, onClick = onLogout, modifier = Modifier.padding(horizontal = 12.dp))
            Spacer(Modifier.weight(1f))
            Text("SelfXTrack ${com.selfxtrack.app.BuildConfig.VERSION_NAME}", Modifier.padding(24.dp),
                style = MaterialTheme.typography.labelSmall, color = Color.Gray)
        }
    }
}

@Composable
private fun MenuItem(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, subtitle: String, onClick: () -> Unit) {
    NavigationDrawerItem(
        icon = { Icon(icon, null, tint = MaterialTheme.colorScheme.primary) },
        label = {
            Column(Modifier.padding(vertical = 6.dp)) {
                Text(title, fontWeight = FontWeight.SemiBold)
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = Color.Gray)
            }
        },
        selected = false, onClick = onClick, modifier = Modifier.padding(horizontal = 12.dp))
}

@Composable
private fun DeviceCard(d: Device, b: com.selfxtrack.app.data.Brief?, onOpen: (String) -> Unit, onSos: (Int) -> Unit,
                       onSetup: (String) -> Unit, onAsk: (String) -> Unit) {
    val sos = d.active_sos != null
    val accent = when { sos -> Color(0xFFC62828); d.online -> Color(0xFF2E7D32); else -> Color.Gray }
    val low = (d.battery ?: 100) <= 15
    ElevatedCard(
        onClick = { if (sos) onSos(d.active_sos!!) else onOpen(d.device_id) }, modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.elevatedCardColors(containerColor = if (sos) Color(0xFFFFEBEE) else Color.White)
    ) {
        Column {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Box {
                Box(Modifier.size(52.dp).clip(CircleShape).background(accent.copy(alpha = 0.12f)), contentAlignment = Alignment.Center) {
                    Icon(when (d.kind) { "elderly" -> Icons.Default.Elderly; "pet" -> Icons.Default.Pets
                        "bike" -> Icons.Default.TwoWheeler; "bag" -> Icons.Default.Backpack; else -> Icons.Default.ChildCare },
                        null, Modifier.size(30.dp), tint = if (sos) accent else MaterialTheme.colorScheme.primary)
                }
                Box(Modifier.size(14.dp).align(Alignment.BottomEnd).clip(CircleShape).background(Color.White).padding(2.dp)
                    .clip(CircleShape).background(accent))                                  // online / offline / SOS dot
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(d.name ?: d.device_id, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.weight(1f, fill = false))
                    Spacer(Modifier.width(8.dp))
                    Surface(shape = RoundedCornerShape(10.dp), color = (if (low) Color(0xFFC62828) else Color(0xFF2E7D32)).copy(alpha = 0.12f)) {
                        Row(Modifier.padding(horizontal = 6.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(if (d.charging) Icons.Default.BatteryChargingFull else Icons.Default.BatteryStd, null, Modifier.size(14.dp),
                                tint = if (low) Color(0xFFC62828) else Color(0xFF2E7D32))
                            Text("${d.battery ?: "–"}%", style = MaterialTheme.typography.labelSmall,
                                color = if (low) Color(0xFFC62828) else Color(0xFF2E7D32))
                        }
                    }
                }
                Text(briefMain(d, b), color = if (sos) accent else if (b?.state == "offline") Color.Gray else Color(0xFF202124),
                    style = MaterialTheme.typography.bodyMedium, fontWeight = if (sos) FontWeight.Bold else FontWeight.Normal)
                briefDetail(d, b)?.let { Text(it, color = Color(0xFF5F6368), style = MaterialTheme.typography.bodySmall) }
            }
            // ✨ = "Ask about <child>" (chat, voice, AI language)
            IconButton(onClick = { onAsk(d.device_id) }) {
                Icon(Icons.Default.AutoAwesome, t("Ask about {0}", d.name ?: d.device_id), tint = MaterialTheme.colorScheme.primary)
            }
            IconButton(onClick = { onSetup(d.device_id) }) { Icon(Icons.Default.Settings, t("Child setup"), tint = Color.Gray) }
        }
        if (!sos) BriefNotes(b)
        }
    }
}


/** Account & privacy (DPDP): policy, export my data, delete my account. */
@Composable
fun AccountDialog(onClose: () -> Unit, onDeleted: () -> Unit) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val scope = rememberCoroutineScope()
    var askDelete by remember { mutableStateOf(false) }
    var pw by remember { mutableStateOf("") }
    var msg by remember { mutableStateOf<String?>(null) }
    val server = Api.session.server.trimEnd('/')
    fun open(path: String) = ctx.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW,
        android.net.Uri.parse(server + path)))
    AlertDialog(onDismissRequest = onClose, title = { Text(t("Account & privacy")) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                TextButton(onClick = { open("/privacy") }) { Text(t("📄 Privacy Policy")) }
                TextButton(onClick = { open("/terms") }) { Text(t("📄 Terms of Use")) }
                TextButton(onClick = {
                    scope.launch {
                        runCatching { Api.api.exportData().string() }.onSuccess { json ->
                            ctx.startActivity(android.content.Intent.createChooser(android.content.Intent(android.content.Intent.ACTION_SEND)
                                .setType("application/json").putExtra(android.content.Intent.EXTRA_TEXT, json), t("Save / share my data")))
                        }.onFailure { msg = it.userMessage() }
                    }
                }) { Text(t("⬇️ Download my data")) }
                if (!askDelete) TextButton(onClick = { askDelete = true }) {
                    Text(t("🗑 Delete my account"), color = MaterialTheme.colorScheme.error)
                } else {
                    Text(t("This permanently deletes your account. Trackers you own are released and their history is erased. Enter your password to confirm."), style = MaterialTheme.typography.bodySmall)
                    OutlinedTextField(pw, { pw = it }, label = { Text(t("Password")) },
                        visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation())
                    Button(enabled = pw.length >= 6, colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                        onClick = { scope.launch {
                            runCatching { Api.api.deleteAccount(DeleteReq(pw)) }
                                .onSuccess { Api.session.logout(); onDeleted() }.onFailure { msg = it.userMessage() }
                        } }) { Text(t("Delete permanently")) }
                }
                msg?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        }, confirmButton = { TextButton(onClick = onClose) { Text(t("Close")) } })
}
