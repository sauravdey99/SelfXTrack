package com.selfxtrack.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.selfxtrack.app.data.*
import com.selfxtrack.app.i18n.t
import kotlinx.coroutines.launch
import org.osmdroid.events.MapListener
import org.osmdroid.events.ScrollEvent
import org.osmdroid.events.ZoomEvent
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.overlay.Polygon

// ---------------------------------------------------------------- look & labels
val PLACE_KINDS = listOf("home", "school", "class", "activity", "family", "other")

fun placeEmoji(kind: String) = when (kind) {
    "home" -> "🏠"; "school" -> "🏫"; "class" -> "📚"; "activity" -> "⚽"; "family" -> "👵"; else -> "📍"
}

fun placeColor(kind: String) = when (kind) {
    "home" -> Color(0xFF2E7D32); "school" -> Color(0xFF1F4E79); "class" -> Color(0xFF6A1B9A)
    "activity" -> Color(0xFFEF6C00); "family" -> Color(0xFFAD1457); else -> Color(0xFF546E7A)
}

fun placeKindLabel(kind: String) = when (kind) {
    "home" -> t("Home"); "school" -> t("School"); "class" -> t("Tuition / class"); "activity" -> t("Activity / sport")
    "family" -> t("Family / friends"); else -> t("Other")
}

private fun kindHint(kind: String) = when (kind) {
    "home" -> t("e.g. Home"); "school" -> t("e.g. DPS School"); "class" -> t("e.g. Maths tuition")
    "activity" -> t("e.g. Swimming, Dance, Cricket"); "family" -> t("e.g. Grandma's house"); else -> t("Name of the place")
}

private fun rolesFor(kind: String) = when (kind) {
    "school" -> listOf("teacher", "staff", "other"); "class" -> listOf("tutor", "staff", "other")
    "activity" -> listOf("coach", "staff", "other"); "family" -> listOf("caretaker", "other")
    else -> listOf("caretaker", "staff", "other")
}

fun personRoleLabel(r: String) = when (r) {
    "teacher" -> t("Teacher"); "staff" -> t("Staff"); "coach" -> t("Coach"); "tutor" -> t("Tutor")
    "caretaker" -> t("Caretaker"); "driver" -> t("Driver"); else -> t("Other")
}

private val DAY_KEYS = listOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
private fun dayLabel(i: Int) = t(DAY_KEYS[i])

/** First n whole letters (a letter + its vowel signs counts as one), so Indian scripts are not cut mid-letter. */
private fun graphemes(s: String, n: Int): String {
    val bi = java.text.BreakIterator.getCharacterInstance()
    bi.setText(s)
    var end = 0
    repeat(n) { val e = bi.next(); if (e == java.text.BreakIterator.DONE) return s; end = e }
    return s.substring(0, end)
}

/** Labels for the 7 round day buttons: as short as possible (2 letters) but always different from each other
 *  (e.g. Urdu جمعرات / جمعہ need 4). */
private fun dayButtonLabels(): List<String> {
    val full = (0..6).map { dayLabel(it) }
    for (n in 2..6) {
        val short = full.map { graphemes(it, n) }
        if (short.toSet().size == 7) return short
    }
    return full
}

/** "Mon–Fri 08:00–14:30 · Sat 07:00–08:00" (or "Any time"). */
fun scheduleText(slots: List<Slot>): String {
    if (slots.isEmpty()) return t("Any time")
    return slots.joinToString(" · ") { s -> daysText(s.days) + " " + s.start + "–" + s.end }
}

private fun daysText(days: List<Int>): String {
    val d = days.sorted()
    return when {
        d == (0..6).toList() -> t("Every day")
        d == (0..4).toList() -> dayLabel(0) + "–" + dayLabel(4)
        d == listOf(5, 6) -> t("Weekend")
        d.size >= 3 && d.zipWithNext().all { (a, b) -> b == a + 1 } -> dayLabel(d.first()) + "–" + dayLabel(d.last())
        else -> d.joinToString(", ") { dayLabel(it) }
    }
}

private fun placeCircle(lat: Double, lon: Double, r: Int, kind: String, title: String): Polygon = Polygon().apply {
    points = Polygon.pointsAsCircle(GeoPoint(lat, lon), r.toDouble())
    val c = placeColor(kind)
    fun argb(a: Int) = (a shl 24) or ((c.red * 255).toInt() shl 16) or ((c.green * 255).toInt() shl 8) or (c.blue * 255).toInt()
    fillPaint.color = argb(0x33)
    outlinePaint.color = argb(0xFF)
    outlinePaint.strokeWidth = 4f
    this.title = title
}

@Composable
fun KindBadge(kind: String, size: Int = 44) {
    Box(Modifier.size(size.dp).clip(CircleShape).background(placeColor(kind).copy(alpha = 0.14f)),
        contentAlignment = Alignment.Center) { Text(placeEmoji(kind), fontSize = (size * 0.48).sp) }
}

// ---------------------------------------------------------------- list of places
/** All places of one child: map overview + list. Tap a place to edit it, + to add. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlacesListScreen(deviceId: String, onBack: () -> Unit, onEdit: (Int) -> Unit) {
    val ctx = LocalContext.current
    var list by remember { mutableStateOf<List<ChildPlace>?>(null) }
    var msg by remember { mutableStateOf<String?>(null) }
    var name by remember { mutableStateOf("") }
    val map = remember { newMapView(ctx) }
    LaunchedEffect(Unit) {
        runCatching { Api.api.device(deviceId) }.onSuccess { d -> name = d.name ?: deviceId }
        runCatching { Api.api.places(deviceId) }.onSuccess { list = it; msg = null }.onFailure { msg = it.userMessage() }
    }
    Scaffold(topBar = {
        TopAppBar(title = { Text(t("📍 {0}'s places", name)) },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) } })
    }, floatingActionButton = {
        ExtendedFloatingActionButton(onClick = { onEdit(0) }, icon = { Icon(Icons.Default.Add, null) },
            text = { Text(t("Add place")) })
    }) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            val places = list
            if (!places.isNullOrEmpty()) {
                AndroidView({ map }, Modifier.fillMaxWidth().height(200.dp).clipToBounds()) { m ->
                    m.overlays.clear()
                    places.forEach { p -> m.overlays.add(placeCircle(p.lat, p.lon, p.radius_m, p.kind, p.name)) }
                    val home = places.firstOrNull { it.kind == "home" } ?: places.first()
                    m.controller.setCenter(GeoPoint(home.lat, home.lon))
                    m.controller.setZoom(if (places.size > 1) 13.0 else 16.0)
                    m.invalidate()
                }
            }
            msg?.let { Text(it, Modifier.padding(12.dp), color = MaterialTheme.colorScheme.error) }
            when {
                places == null && msg == null -> Box(Modifier.fillMaxWidth().padding(32.dp), Alignment.Center) { CircularProgressIndicator() }
                places.isNullOrEmpty() -> EmptyPlaces(onAdd = { onEdit(0) })
                else -> LazyColumn(contentPadding = PaddingValues(12.dp, 12.dp, 12.dp, 88.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(places, key = { it.id }) { p -> PlaceRow(p) { onEdit(p.id) } }
                }
            }
        }
    }
}

@Composable
private fun EmptyPlaces(onAdd: () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("🏠 🏫 📚 ⚽ 👵", fontSize = 30.sp)
        Text(t("Add the places your child goes to"), fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
        Text(t("Home, school, tuition, swimming, grandma's house … You get an alert on arrival and departure, and if your child is late."),
            color = Color.Gray, textAlign = TextAlign.Center)
        Button(onClick = onAdd) { Icon(Icons.Default.Add, null); Text(" " + t("Add place")) }
    }
}

@Composable
fun PlaceRow(p: ChildPlace, onClick: () -> Unit) {
    ElevatedCard(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            KindBadge(p.kind)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(p.name, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false))
                    if (p.inside == true) {
                        Spacer(Modifier.width(8.dp))
                        Text(t("● here now"), color = Color(0xFF2E7D32), style = MaterialTheme.typography.labelSmall)
                    }
                }
                Text(placeKindLabel(p.kind) + (p.note?.let { " · $it" } ?: ""), color = Color.Gray,
                    style = MaterialTheme.typography.bodySmall)
                Text("🕒 " + scheduleText(p.schedule), style = MaterialTheme.typography.bodySmall,
                    maxLines = 2, overflow = TextOverflow.Ellipsis)
                if (p.people.isNotEmpty()) Text("👤 " + p.people.joinToString(", ") { it.name },
                    style = MaterialTheme.typography.bodySmall, color = placeColor(p.kind), maxLines = 1,
                    overflow = TextOverflow.Ellipsis)
            }
            Icon(Icons.Default.ChevronRight, null, tint = Color.Gray)
        }
    }
}

// ---------------------------------------------------------------- add / edit one place
/** placeId 0 = new place. People can be added before the first save; they are stored with the place. */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun PlaceEditorScreen(deviceId: String, placeId: Int, onDone: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val isNew = placeId == 0
    var loaded by remember { mutableStateOf(isNew) }
    var name by remember { mutableStateOf("") }
    var kind by remember { mutableStateOf("other") }
    var note by remember { mutableStateOf("") }
    var radius by remember { mutableFloatStateOf(150f) }
    var center by remember { mutableStateOf<GeoPoint?>(null) }
    var slots by remember { mutableStateOf(listOf<Slot>()) }
    var alertLate by remember { mutableStateOf(true) }
    var notifyEnter by remember { mutableStateOf(true) }
    var notifyExit by remember { mutableStateOf(true) }
    var people by remember { mutableStateOf(listOf<Person>()) }
    var pending by remember { mutableStateOf(listOf<PersonReq>()) }   // added before the first save
    var child by remember { mutableStateOf("") }
    var trackerPos by remember { mutableStateOf<GeoPoint?>(null) }
    var busy by remember { mutableStateOf(false) }
    var err by remember { mutableStateOf<String?>(null) }
    var addingPerson by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }
    var pickTime by remember { mutableStateOf<Triple<Int, Boolean, String>?>(null) }   // slot index, isStart, value
    val map = remember { newMapView(ctx) }

    LaunchedEffect(Unit) {
        runCatching { Api.api.device(deviceId) }.onSuccess { d ->
            child = d.name ?: deviceId
            if (d.last_lat != null && d.last_lon != null) trackerPos = GeoPoint(d.last_lat, d.last_lon)
        }
        if (!isNew) runCatching { Api.api.places(deviceId).first { it.id == placeId } }.onSuccess { p ->
            name = p.name; kind = p.kind; note = p.note ?: ""; radius = p.radius_m.toFloat(); center = GeoPoint(p.lat, p.lon)
            slots = p.schedule; alertLate = p.alert_late; notifyEnter = p.notify_enter; notifyExit = p.notify_exit
            people = p.people; loaded = true
        }.onFailure { err = it.userMessage(); loaded = true }
        val start = center ?: trackerPos
        if (start != null) map.controller.setCenter(start)
        else { map.controller.setCenter(GeoPoint(20.59, 78.96)); map.controller.setZoom(5.0) }   // India
        center = center ?: start
    }
    DisposableEffect(Unit) {
        // dragging the map must move the map, not scroll the page around it
        @Suppress("ClickableViewAccessibility")
        map.setOnTouchListener { v, _ -> v.parent?.requestDisallowInterceptTouchEvent(true); false }
        val l = object : MapListener {
            override fun onScroll(event: ScrollEvent?): Boolean { center = GeoPoint(map.mapCenter.latitude, map.mapCenter.longitude); return true }
            override fun onZoom(event: ZoomEvent?): Boolean { center = GeoPoint(map.mapCenter.latitude, map.mapCenter.longitude); return true }
        }
        map.addMapListener(l)
        onDispose { map.removeMapListener(l) }
    }

    fun save() {
        val c = center ?: run { err = t("Move the map to the place first."); return }
        busy = true; err = null
        val req = PlaceReq(name.trim(), kind, c.latitude, c.longitude, radius.toInt(), note.trim().ifBlank { null }, slots,
            alertLate, notifyEnter, notifyExit)
        scope.launch {
            runCatching {
                val saved = if (isNew) Api.api.addPlace(deviceId, req) else Api.api.editPlace(deviceId, placeId, req)
                pending.forEach { Api.api.addPerson(deviceId, saved.id, it) }
                saved
            }.onSuccess { onDone() }.onFailure { err = it.userMessage(); busy = false }
        }
    }

    Scaffold(topBar = {
        TopAppBar(title = { Text(if (isNew) t("New place") else t("Edit place")) },
            navigationIcon = { IconButton(onClick = onDone) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) } },
            actions = { if (!isNew) IconButton(onClick = { confirmDelete = true }) { Icon(Icons.Default.Delete, t("Delete")) } })
    }, bottomBar = {
        Surface(tonalElevation = 3.dp) {
            Column(Modifier.fillMaxWidth().navigationBarsPadding().padding(12.dp)) {
                err?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(bottom = 6.dp)) }
                Button(onClick = ::save, enabled = !busy && loaded && name.isNotBlank(), modifier = Modifier.fillMaxWidth().height(50.dp)) {
                    if (busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    else Text(if (isNew) t("Save place") else t("Save changes"), fontWeight = FontWeight.Bold)
                }
            }
        }
    }) { pad ->
        Column(Modifier.padding(pad).fillMaxSize().verticalScroll(rememberScrollState())) {
            // ---- where (clipToBounds: the map view would otherwise draw over the content below)
            Box(Modifier.fillMaxWidth().height(250.dp).clipToBounds()) {
                AndroidView({ map }, Modifier.fillMaxSize()) { m ->
                    m.overlays.clear()
                    center?.let { c -> m.overlays.add(placeCircle(c.latitude, c.longitude, radius.toInt(), kind, name)) }
                    m.invalidate()
                }
                Text(placeEmoji(kind), fontSize = 30.sp, modifier = Modifier.align(Alignment.Center).offset(y = (-16).dp))
                Surface(Modifier.align(Alignment.TopCenter).padding(8.dp), shape = RoundedCornerShape(20.dp),
                    color = Color.White.copy(alpha = 0.92f), shadowElevation = 2.dp) {
                    Text(t("Move the map so the pin is on the place"), Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                        style = MaterialTheme.typography.labelMedium)
                }
                trackerPos?.let { tp ->
                    SmallFloatingActionButton(onClick = { map.controller.animateTo(tp) },
                        modifier = Modifier.align(Alignment.BottomEnd).padding(10.dp)) {
                        Icon(Icons.Default.MyLocation, t("Where {0} is now", child))
                    }
                }
            }
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Column {
                    Text(t("Area size: {0} m", radius.toInt()), style = MaterialTheme.typography.labelLarge)
                    Slider(radius, { radius = it }, valueRange = 50f..1000f, steps = 18)
                }
                // ---- what
                Text(t("Type of place"), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    PLACE_KINDS.forEach { k ->
                        FilterChip(selected = kind == k, onClick = { kind = k },
                            label = { Text(placeEmoji(k) + "  " + placeKindLabel(k)) },
                            colors = FilterChipDefaults.filterChipColors(selectedContainerColor = placeColor(k).copy(alpha = 0.18f)))
                    }
                }
                OutlinedTextField(name, { name = it }, label = { Text(t("Name")) }, placeholder = { Text(kindHint(kind)) },
                    singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(note, { note = it }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                    label = { Text(if (kind == "school") t("Class (e.g. 5A)") else t("Note (optional)")) })

                // ---- when
                HorizontalDivider()
                Text(t("When does {0} go here?", child.ifBlank { t("your child") }), style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold)
                Text(if (slots.isEmpty()) t("No fixed time – you still get arrival and departure alerts.")
                     else t("You'll be alerted if {0} is not there 15 min after the start, or leaves early.", child.ifBlank { t("your child") }),
                    color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                slots.forEachIndexed { i, s ->
                    SlotEditor(s, kind, onChange = { n -> slots = slots.toMutableList().also { it[i] = n } },
                        onPickStart = { pickTime = Triple(i, true, s.start) }, onPickEnd = { pickTime = Triple(i, false, s.end) },
                        onRemove = { slots = slots.toMutableList().also { it.removeAt(i) } })
                }
                OutlinedButton(onClick = {
                    val preset = when (kind) {
                        "school" -> Slot(listOf(0, 1, 2, 3, 4), "08:00", "14:00")
                        "class" -> Slot(listOf(0, 2, 4), "17:00", "18:00")
                        "activity" -> Slot(listOf(5), "07:00", "08:00")
                        else -> Slot(listOf(5, 6), "10:00", "12:00")
                    }
                    slots = slots + preset
                }, enabled = slots.size < 14) { Icon(Icons.Default.Schedule, null); Text("  " + t("Add time")) }

                // ---- alerts
                HorizontalDivider()
                Text(t("Alerts"), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                SwitchRow(t("When {0} arrives", child.ifBlank { t("your child") }), notifyEnter) { notifyEnter = it }
                SwitchRow(t("When {0} leaves", child.ifBlank { t("your child") }), notifyExit) { notifyExit = it }
                SwitchRow(t("If late or leaves early"), alertLate && slots.isNotEmpty(), enabled = slots.isNotEmpty()) { alertLate = it }

                // ---- people
                HorizontalDivider()
                Text(t("People at this place"), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                Text(t("In an emergency you can alert them with one tap. If they use SelfXTrack with this number, they also see {0} on their dashboard – only after you alert them.",
                    child.ifBlank { t("your child") }), color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                people.forEach { p ->
                    PersonRow(p.name, p.phone, p.role) {
                        scope.launch { runCatching { Api.api.removePerson(deviceId, placeId, p.id) }
                            .onSuccess { people = it.people }.onFailure { err = it.userMessage() } }
                    }
                }
                pending.forEachIndexed { i, p ->
                    PersonRow(p.name, p.phone, p.role, saved = false) { pending = pending.toMutableList().also { it.removeAt(i) } }
                }
                if (people.size + pending.size < 10) OutlinedButton(onClick = { addingPerson = true }) {
                    Icon(Icons.Default.PersonAdd, null); Text("  " + t("Add person"))
                }
                Spacer(Modifier.height(8.dp))
            }
        }
    }

    pickTime?.let { (i, isStart, value) ->
        TimeDialog(value, title = if (isStart) t("Starts at") else t("Ends at"), onDismiss = { pickTime = null }) { v ->
            val s = slots[i]
            slots = slots.toMutableList().also { it[i] = if (isStart) s.copy(start = v) else s.copy(end = v) }
            pickTime = null
        }
    }
    if (addingPerson) PersonDialog(kind, onDismiss = { addingPerson = false }) { req ->
        addingPerson = false
        if (isNew) pending = pending + req
        else scope.launch { runCatching { Api.api.addPerson(deviceId, placeId, req) }
            .onSuccess { people = it.people }.onFailure { err = it.userMessage() } }
    }
    if (confirmDelete) AlertDialog(onDismissRequest = { confirmDelete = false },
        title = { Text(t("Delete {0}?", name)) },
        text = { Text(t("Its alerts, times and people will be removed.")) },
        confirmButton = { TextButton(onClick = {
            confirmDelete = false
            scope.launch { runCatching { Api.api.deletePlace(deviceId, placeId) }.onSuccess { onDone() }.onFailure { err = it.userMessage() } }
        }) { Text(t("Delete"), color = MaterialTheme.colorScheme.error) } },
        dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text(t("Cancel")) } })
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SlotEditor(s: Slot, kind: String, onChange: (Slot) -> Unit, onPickStart: () -> Unit, onPickEnd: () -> Unit,
                       onRemove: () -> Unit) {
    val bad = s.end <= s.start || s.days.isEmpty()
    OutlinedCard(Modifier.fillMaxWidth(), border = androidx.compose.foundation.BorderStroke(1.dp,
        if (bad) MaterialTheme.colorScheme.error else placeColor(kind).copy(alpha = 0.4f))) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            val labels = dayButtonLabels()
            val small = labels.any { it.length > 3 }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
                (0..6).forEach { d ->
                    val on = d in s.days
                    Box(Modifier.weight(1f).aspectRatio(1f).clip(CircleShape)
                        .background(if (on) placeColor(kind) else Color.Transparent)
                        .border(1.dp, placeColor(kind).copy(alpha = 0.5f), CircleShape)
                        .clickable { onChange(s.copy(days = if (on) s.days - d else (s.days + d).sorted())) },
                        contentAlignment = Alignment.Center) {
                        Text(labels[d], color = if (on) Color.White else placeColor(kind), fontSize = if (small) 10.sp else 12.sp,
                            fontWeight = FontWeight.Bold, maxLines = 1, softWrap = false)
                    }
                }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf(t("Mon–Fri") to (0..4).toList(), t("Weekend") to listOf(5, 6), t("Every day") to (0..6).toList())
                    .forEach { (label, days) ->
                        AssistChip(onClick = { onChange(s.copy(days = days)) }, label = { Text(label, fontSize = 12.sp) })
                    }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                TimeButton(t("From"), s.start, Modifier.weight(1f), onPickStart)
                // auto-mirrored: points the reading direction (also right-to-left for Urdu)
                Icon(Icons.AutoMirrored.Filled.ArrowForward, null, Modifier.padding(horizontal = 6.dp).size(18.dp), tint = Color.Gray)
                TimeButton(t("To"), s.end, Modifier.weight(1f), onPickEnd)
                IconButton(onClick = onRemove) { Icon(Icons.Default.Close, t("Remove")) }
            }
            if (bad) Text(if (s.days.isEmpty()) t("Choose at least one day") else t("End time must be after start time"),
                color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun TimeButton(label: String, value: String, modifier: Modifier, onClick: () -> Unit) {
    OutlinedButton(onClick = onClick, modifier = modifier, contentPadding = PaddingValues(8.dp)) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(label, style = MaterialTheme.typography.labelSmall, color = Color.Gray)
            Text(value, fontWeight = FontWeight.Bold, fontSize = 18.sp)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TimeDialog(value: String, title: String, onDismiss: () -> Unit, onPick: (String) -> Unit) {
    val (h, m) = value.split(":").map { it.toIntOrNull() ?: 0 }.let { (it.getOrNull(0) ?: 8) to (it.getOrNull(1) ?: 0) }
    val st = rememberTimePickerState(initialHour = h, initialMinute = m, is24Hour = true)
    AlertDialog(onDismissRequest = onDismiss, title = { Text(title) },
        text = { TimePicker(state = st) },
        confirmButton = { TextButton(onClick = { onPick("%02d:%02d".format(st.hour, st.minute)) }) { Text(t("OK")) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(t("Cancel")) } })
}

@Composable
private fun SwitchRow(label: String, checked: Boolean, enabled: Boolean = true, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f), color = if (enabled) Color.Unspecified else Color.Gray)
        Switch(checked, onChange, enabled = enabled)
    }
}

@Composable
private fun PersonRow(name: String, phone: String, role: String, saved: Boolean = true, onRemove: () -> Unit) {
    val ctx = LocalContext.current
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(38.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primary.copy(alpha = 0.1f)),
            contentAlignment = Alignment.Center) { Text(name.take(1).uppercase(), fontWeight = FontWeight.Bold) }
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text(name + " · " + personRoleLabel(role), fontWeight = FontWeight.SemiBold)
            Text(phone + if (saved) "" else "  " + t("(saved with the place)"), color = Color.Gray,
                style = MaterialTheme.typography.bodySmall)
        }
        if (saved) IconButton(onClick = { ctx.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$phone"))) }) {
            Icon(Icons.Default.Call, t("Call"))
        }
        IconButton(onClick = onRemove) { Icon(Icons.Default.Delete, t("Remove")) }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PersonDialog(kind: String, onDismiss: () -> Unit, onAdd: (PersonReq) -> Unit) {
    val roles = rolesFor(kind)
    var name by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var role by remember { mutableStateOf(roles.first()) }
    val digits = phone.filter { it.isDigit() }
    AlertDialog(onDismissRequest = onDismiss, title = { Text(t("Add person")) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    roles.forEach { r -> FilterChip(role == r, { role = r }, { Text(personRoleLabel(r)) }) }
                }
                OutlinedTextField(name, { name = it }, label = { Text(t("Name")) }, singleLine = true)
                OutlinedTextField(phone, { phone = phoneChars(it) }, label = { Text(t("Mobile number")) }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                    supportingText = { Text(t("They get an SMS with the live location in an emergency.")) })
            }
        },
        confirmButton = { TextButton(enabled = name.isNotBlank() && digits.length >= 10,
            onClick = { onAdd(PersonReq(name.trim(), phone.trim(), role)) }) { Text(t("Add")) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(t("Cancel")) } })
}

/** Phone fields: only digits, + and spaces / dashes, max 16 characters. */
private fun phoneChars(v: String) = v.filter { it.isDigit() || it in "+ -" }.take(16)

// ---------------------------------------------------------------- transport (in Child setup)
val TRANSPORT_KINDS = listOf("bus", "van", "auto", "cab", "other")

fun transportEmoji(k: String) = when (k) { "bus" -> "🚌"; "van" -> "🚐"; "auto" -> "🛺"; "cab" -> "🚕"; else -> "🚗" }

fun transportKindLabel(k: String) = when (k) {
    "bus" -> t("Bus"); "van" -> t("Van"); "auto" -> t("Auto"); "cab" -> t("Cab"); else -> t("Other")
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TransportDialog(existing: Transport?, places: List<ChildPlace>, onDismiss: () -> Unit, onSave: (TransportReq) -> Unit,
                    onDelete: (() -> Unit)? = null) {
    var name by remember { mutableStateOf(existing?.name ?: "") }
    var kind by remember { mutableStateOf(existing?.kind ?: "bus") }
    var driver by remember { mutableStateOf(existing?.driver_name ?: "") }
    var phone by remember { mutableStateOf(existing?.driver_phone ?: "") }
    var hasBeacon by remember { mutableStateOf(existing?.beacon_id != null) }
    var beacon by remember { mutableStateOf(existing?.beacon_id ?: "") }
    var used by remember { mutableStateOf(existing?.place_ids?.toSet() ?: emptySet()) }
    var all by remember { mutableStateOf(false) }
    val phoneOk = phone.isBlank() || phone.filter { it.isDigit() }.length >= 10
    AlertDialog(onDismissRequest = onDismiss,
        title = { Text(if (existing == null) t("Add transport") else t("Edit transport")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    TRANSPORT_KINDS.forEach { k ->
                        FilterChip(kind == k, { kind = k }, { Text(transportEmoji(k) + " " + transportKindLabel(k)) })
                    }
                }
                OutlinedTextField(name, { name = it }, label = { Text(t("Name")) }, singleLine = true,
                    placeholder = { Text(t("e.g. School bus 12, Swimming van")) })
                OutlinedTextField(driver, { driver = it }, label = { Text(t("Driver name (optional)")) }, singleLine = true)
                OutlinedTextField(phone, { phone = phoneChars(it) }, label = { Text(t("Driver mobile (optional)")) }, singleLine = true,
                    isError = !phoneOk, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone))
                if (places.isNotEmpty()) {
                    Text(t("Used for"), style = MaterialTheme.typography.labelLarge)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        places.forEach { p ->
                            FilterChip(p.id in used, { used = if (p.id in used) used - p.id else used + p.id },
                                { Text(placeEmoji(p.kind) + " " + p.name) })
                        }
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(hasBeacon, { hasBeacon = it })
                    Text(t("It has a SelfXTrack beacon (boarded / got off alerts)"), style = MaterialTheme.typography.bodySmall)
                }
                if (hasBeacon) OutlinedTextField(beacon, { beacon = it.uppercase() }, singleLine = true,
                    label = { Text(t("Beacon ID (printed on the beacon)")) })
                if (existing == null) Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(all, { all = it }); Text(t("All my children use it"), style = MaterialTheme.typography.bodySmall)
                }
                if (onDelete != null) TextButton(onClick = onDelete) {
                    Icon(Icons.Default.Delete, null, tint = MaterialTheme.colorScheme.error)
                    Text(" " + t("Delete"), color = MaterialTheme.colorScheme.error)
                }
            }
        },
        confirmButton = { TextButton(enabled = name.isNotBlank() && phoneOk && (!hasBeacon || beacon.trim().length >= 3),
            onClick = { onSave(TransportReq(name.trim(), kind, beacon.trim().takeIf { hasBeacon && it.isNotBlank() },
                driver.trim().ifBlank { null }, phone.trim().ifBlank { null }, used.toList(), all)) }) { Text(t("Save")) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(t("Cancel")) } })
}
