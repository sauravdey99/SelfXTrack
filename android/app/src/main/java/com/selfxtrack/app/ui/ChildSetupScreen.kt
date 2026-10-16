package com.selfxtrack.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.selfxtrack.app.data.*
import com.selfxtrack.app.i18n.t
import kotlinx.coroutines.launch

/** Display label for a tracker kind value sent to / received from the server. */
private fun kindLabel(k: String): String = when (k) {
    "child" -> t("Child"); "elderly" -> t("Elderly"); "pet" -> t("Pet"); "bike" -> t("Bike"); "bag" -> t("Bag"); else -> k
}

/** Display label for a school contact role value. */
private fun roleLabel(r: String): String = when (r) {
    "teacher" -> t("Teacher"); "staff" -> t("Staff"); "other" -> t("Other"); else -> r
}

/** One-time setup for each tracker: name, places (any number, with times + people), transport, family. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChildSetupScreen(deviceId: String, isNew: Boolean, onBack: () -> Unit,
                     onZones: (String) -> Unit, onContacts: (String) -> Unit, onPlace: (String, Int) -> Unit = { _, _ -> }) {
    val scope = rememberCoroutineScope()
    var setup by remember { mutableStateOf<ChildSetup?>(null) }
    var msg by remember { mutableStateOf<String?>(null) }
    var dialog by remember { mutableStateOf<String?>(null) }   // name / school / family

    suspend fun load() { runCatching { Api.api.setup(deviceId) }.onSuccess { setup = it }.onFailure { msg = it.userMessage() } }
    LaunchedEffect(Unit) { load() }

    Scaffold(topBar = {
        TopAppBar(title = { Text(t("Child setup")) },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) } })
    }) { pad ->
        val s = setup
        Column(Modifier.padding(pad).padding(16.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (isNew) Text(t("✅ Tracker added. Set it up once – you can change it any time from ⚙️ on the child's card."),
                color = Color(0xFF2E7D32))
            msg?.let { Text(it, color = MaterialTheme.colorScheme.secondary) }
            if (s == null) { CircularProgressIndicator(); return@Column }

            Section(Icons.Default.ChildCare, t("Child"), s.name ?: s.device_id,
                t("Type: {0} · Tracker {1}", kindLabel(s.kind), s.device_id), t("Edit")) { dialog = "name" }

            if (s.kind == "elderly") CareCard(deviceId)
            PlacesCard(deviceId, s.name ?: s.device_id, onAll = { onZones(deviceId) }, onPlace = { onPlace(deviceId, it) })
            TransportCard(deviceId)
            // moved here from Insights: holidays are part of the child's setup (routine alerts pause on these days)
            Section(Icons.Default.BeachAccess, t("Holidays"), t("School holidays, trips, sick days"),
                t("On these days late / missed-place alerts pause. SOS always works."), t("Edit")) { dialog = "holidays" }
            OldSchoolContactsCard(deviceId)

            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Group, null, Modifier.size(30.dp), tint = MaterialTheme.colorScheme.primary)
                        Spacer(Modifier.width(12.dp))
                        Column {
                            Text(t("Family"), fontWeight = FontWeight.Bold)
                            Text(t("Shared with all your children – add once. Parents get the SOS alarm at once, family after 2 min."), color = Color.Gray,
                                style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    s.family.forEach { f ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text((f.name ?: f.email) + " · " + when (f.role) { "owner" -> t("owner"); "parent" -> t("parent"); else -> t("family") })
                                Text((f.phone ?: f.email) + "  " + t("✅ added"), color = Color(0xFF2E7D32),
                                    style = MaterialTheme.typography.bodySmall)
                            }
                            if (f.role != "owner" && f.phone != null) TextButton(onClick = { scope.launch {
                                val to = if (f.role == "parent") "family" else "parent"
                                runCatching { Api.api.setRole(deviceId, f.phone, RoleReq(to)) }.onSuccess {
                                    setup = it; msg = if (to == "parent") t("{0} is now a parent – alarm rings immediately.", f.name)
                                                      else t("{0} is now family – alarm after 2 min.", f.name) }
                                    .onFailure { msg = it.userMessage() } } }) { Text(if (f.role == "parent") t("Make family") else t("Make parent")) }
                            if (f.role != "owner" && f.phone != null) IconButton(onClick = { scope.launch {
                                runCatching { Api.api.removeFamily(deviceId, f.phone) }.onSuccess { setup = it; msg = t("{0} removed from all children.", f.name) }
                                    .onFailure { msg = it.userMessage() } } }) { Icon(Icons.Default.Delete, t("Remove")) }
                        }
                    }
                    s.invites.forEach { inv ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(inv.name + " · " + if (inv.relation == "parent") t("parent") else t("family"))
                                Text(inv.phone + "  " + if (inv.ready) t("🟢 registered – accept?") else t("⏳ waiting to register"),
                                    color = if (inv.ready) Color(0xFF2E7D32) else Color.Gray, style = MaterialTheme.typography.bodySmall)
                            }
                            if (inv.ready) TextButton(onClick = { scope.launch {
                                runCatching { Api.api.acceptFamily(deviceId, inv.id) }.onSuccess { setup = it; msg = t("{0} added.", inv.name) }
                                    .onFailure { msg = it.userMessage() } } }) { Text(t("Accept")) }
                            IconButton(onClick = { scope.launch {
                                runCatching { Api.api.cancelFamily(deviceId, inv.id) }.onSuccess { setup = it } } }) {
                                Icon(Icons.Default.Delete, t("Remove"))
                            }
                        }
                    }
                    OutlinedButton(onClick = { dialog = "family" }) { Icon(Icons.Default.Add, null); Text(" " + t("Add family member")) }
                }
            }
            if (isNew) Button(onClick = onBack, modifier = Modifier.fillMaxWidth()) { Text(t("Done")) }
        }
    }

    val s = setup ?: return
    when (dialog) {
        "holidays" -> HolidaysDialog(deviceId, s.name ?: s.device_id, onDone = { dialog = null })
        "name" -> {
            var name by remember { mutableStateOf(s.name ?: "") }
            var kind by remember { mutableStateOf(s.kind) }
            AlertDialog(onDismissRequest = { dialog = null }, title = { Text(t("Child")) },
                text = {
                    Column {
                        OutlinedTextField(name, { name = it }, label = { Text(t("Name")) })
                        Row(Modifier.padding(top = 8.dp)) {
                            listOf("child", "elderly").forEach { k ->
                                FilterChip(kind == k, { kind = k }, { Text(kindLabel(k)) }, Modifier.padding(end = 6.dp))
                            }
                        }
                    }
                },
                confirmButton = { TextButton(onClick = { scope.launch {
                    runCatching { Api.api.saveSetup(deviceId, SetupReq(name = name, kind = kind)) }.onSuccess { setup = it }
                    dialog = null } }) { Text(t("Save")) } },
                dismissButton = { TextButton(onClick = { dialog = null }) { Text(t("Cancel")) } })
        }
        "family" -> {
            var name by remember { mutableStateOf("") }
            var phone by remember { mutableStateOf("") }
            var relation by remember { mutableStateOf("family") }
            AlertDialog(onDismissRequest = { dialog = null }, title = { Text(t("Add family member")) },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(t("When they register on SelfXTrack with this mobile number, you'll get a request here to accept."))
                        Row {
                            FilterChip(relation == "parent", { relation = "parent" }, { Text(t("Parent")) }, Modifier.padding(end = 6.dp))
                            FilterChip(relation == "family", { relation = "family" }, { Text(t("Family")) })
                        }
                        Text(if (relation == "parent") t("Parent: SOS alarm rings immediately, like yours.")
                             else t("Family: SOS alarm after 2 min if parents don't respond."), style = MaterialTheme.typography.bodySmall)
                        OutlinedTextField(name, { name = it }, label = { Text(t("Name (e.g. Mother, Grandpa)")) })
                        OutlinedTextField(phone, { phone = it }, label = { Text(t("Mobile number")) },
                            keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(
                                keyboardType = androidx.compose.ui.text.input.KeyboardType.Phone))
                    }
                },
                confirmButton = { TextButton(enabled = name.isNotBlank() && phone.length >= 10, onClick = { scope.launch {
                    runCatching { Api.api.inviteFamily(deviceId, InviteReq(name.trim(), phone.trim(), relation)) }
                        .onSuccess { setup = it; msg = if (it.invites.any { i -> i.ready }) t("{0} already uses SelfXTrack – tap Accept.", name)
                                     else t("Request saved. Ask {0} to install SelfXTrack and verify {1}.", name, phone) }
                        .onFailure { msg = it.userMessage() }
                    dialog = null } }) { Text(t("Add")) } },
                dismissButton = { TextButton(onClick = { dialog = null }) { Text(t("Cancel")) } })
        }
    }
}

@Composable
private fun Section(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, value: String, sub: String,
                    action: String, onAction: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, Modifier.size(30.dp), tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.Bold)
                Text(value)
                Text(sub, color = Color.Gray, style = MaterialTheme.typography.bodySmall)
            }
            TextButton(onClick = onAction) { Text(action) }
        }
    }
}

/** Places summary: every place the child goes to (any number) – tap one to edit, or open the full list. */
@Composable
private fun PlacesCard(deviceId: String, child: String, onAll: () -> Unit, onPlace: (Int) -> Unit) {
    var places by remember { mutableStateOf<List<ChildPlace>?>(null) }
    LaunchedEffect(Unit) { runCatching { Api.api.places(deviceId) }.onSuccess { places = it } }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Place, null, Modifier.size(30.dp), tint = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(t("Places"), fontWeight = FontWeight.Bold)
                    Text(t("Where {0} goes – home, school, tuition, swimming, grandma's …", child), color = Color.Gray,
                        style = MaterialTheme.typography.bodySmall)
                }
                if (!places.isNullOrEmpty()) TextButton(onClick = onAll) { Text(t("See all")) }
            }
            val list = places
            when {
                list == null -> LinearProgressIndicator(Modifier.fillMaxWidth())
                list.isEmpty() -> Text(t("No places yet. Add home first, then school and other places."), color = Color.Gray)
                else -> list.take(6).forEach { p -> PlaceRow(p) { onPlace(p.id) } }
            }
            if ((list?.size ?: 0) > 6) TextButton(onClick = onAll) { Text(t("+ {0} more", list!!.size - 6)) }
            OutlinedButton(onClick = { onPlace(0) }, modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Default.Add, null); Text(" " + t("Add place"))
            }
        }
    }
}

/** Transport: school bus, van, auto, cab … with driver and an optional beacon for boarded / got-off alerts. */
@Composable
private fun TransportCard(deviceId: String) {
    val scope = rememberCoroutineScope()
    var list by remember { mutableStateOf<List<Transport>>(emptyList()) }
    var places by remember { mutableStateOf<List<ChildPlace>>(emptyList()) }
    var editing by remember { mutableStateOf<Transport?>(null) }
    var adding by remember { mutableStateOf(false) }
    var err by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        runCatching { Api.api.transports(deviceId) }.onSuccess { list = it }
        runCatching { Api.api.places(deviceId) }.onSuccess { places = it }
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.DirectionsBus, null, Modifier.size(30.dp), tint = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(12.dp))
                Column {
                    Text(t("Transport"), fontWeight = FontWeight.Bold)
                    Text(t("Bus, van, auto or cab – with the driver's number. With a beacon you get “boarded / got off” alerts."),
                        color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                }
            }
            list.forEach { tr ->
                OutlinedCard(onClick = { editing = tr }, modifier = Modifier.fillMaxWidth()) {
                    Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(transportEmoji(tr.kind), style = MaterialTheme.typography.headlineSmall)
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(tr.name + if (tr.on_now) "  " + t("🟢 on board now") else "", fontWeight = FontWeight.SemiBold)
                            val sub = listOfNotNull(transportKindLabel(tr.kind),
                                tr.driver_name?.let { t("Driver: {0}", it) },
                                places.filter { it.id in tr.place_ids }.takeIf { it.isNotEmpty() }?.joinToString(", ") { it.name },
                                tr.beacon_id?.let { t("Beacon {0}", it) })
                            Text(sub.joinToString(" · "), color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                        }
                        Icon(Icons.Default.Edit, t("Edit"), tint = Color.Gray)
                    }
                }
            }
            err?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            OutlinedButton(onClick = { adding = true }, modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Default.Add, null); Text(" " + t("Add transport"))
            }
        }
    }
    if (adding) TransportDialog(null, places, onDismiss = { adding = false }, onSave = { req ->
        scope.launch { runCatching { Api.api.addTransport(deviceId, req) }
            .onSuccess { list = it; adding = false; err = null }.onFailure { err = it.userMessage(); adding = false } }
    })
    editing?.let { tr ->
        TransportDialog(tr, places, onDismiss = { editing = null }, onSave = { req ->
            scope.launch { runCatching { Api.api.editTransport(deviceId, tr.id, req) }
                .onSuccess { list = it; editing = null; err = null }.onFailure { err = it.userMessage(); editing = null } }
        }, onDelete = {
            scope.launch { runCatching { Api.api.deleteTransport(deviceId, tr.id) }.onSuccess { list = it }; editing = null }
        })
    }
}

/** School contacts from before places existed, not linked to a place yet. They still get school emergencies. */
@Composable
private fun OldSchoolContactsCard(deviceId: String) {
    val scope = rememberCoroutineScope()
    var old by remember { mutableStateOf<List<TeacherContact>>(emptyList()) }
    suspend fun load() { runCatching { Api.api.contacts(deviceId) }.onSuccess { l -> old = l.filter { it.place_id == null } } }
    LaunchedEffect(Unit) { load() }
    if (old.isEmpty()) return
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF8E1))) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(t("🏫 School contacts"), fontWeight = FontWeight.Bold)
            Text(t("Add a School place with its location – these contacts then move into it automatically. Until then they still get school emergencies."),
                color = Color.Gray, style = MaterialTheme.typography.bodySmall)
            old.forEach { c ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("${c.name} · ${roleLabel(c.role)}\n${c.phone}", Modifier.weight(1f))
                    IconButton(onClick = { scope.launch { runCatching { Api.api.deleteContact(deviceId, c.id) }; load() } }) {
                        Icon(Icons.Default.Delete, t("Remove"))
                    }
                }
            }
        }
    }
}

/** Elderly care: fall detection + "no movement" alert. */
@Composable
private fun CareCard(deviceId: String) {
    val scope = rememberCoroutineScope()
    var c by remember { mutableStateOf<Care?>(null) }
    LaunchedEffect(Unit) { runCatching { Api.api.care(deviceId) }.onSuccess { c = it } }
    fun save(r: CareReq) = scope.launch { runCatching { Api.api.setCare(deviceId, r) }.onSuccess { c = it } }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(t("🧓 Elderly care"), fontWeight = FontWeight.Bold)
            val x = c ?: run { Text(t("Loading…")); return@Column }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(t("Fall detection"))
                    Text(t("After a hard fall the tracker vibrates for 30 s – press the button to cancel, otherwise the family gets an SOS."),
                        color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                }
                Switch(x.fall_detection, { save(CareReq(fall_detection = it)) })
            }
            Text(t("No-movement alert"), fontWeight = FontWeight.SemiBold)
            Row {
                listOf(0 to t("Off"), 2 to t("{0} h", 2), 3 to t("{0} h", 3), 4 to t("{0} h", 4), 6 to t("{0} h", 6)).forEach { (h, l) ->
                    FilterChip(x.inactivity_hours == h, { save(CareReq(inactivity_hours = h)) }, { Text(l) }, Modifier.padding(end = 4.dp))
                }
            }
            Text(t("Only between {0} and {1} (not at night). Not a medical device.", x.active_from, x.active_to),
                color = Color.Gray, style = MaterialTheme.typography.bodySmall)
            x.last_active_at?.let { Text(t("Last movement {0}", ago(it)), style = MaterialTheme.typography.bodySmall) }
        }
    }
}
