package com.selfxtrack.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.automirrored.filled.VolumeOff
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.selfxtrack.app.data.*
import com.selfxtrack.app.i18n.t
import kotlinx.coroutines.launch
import org.osmdroid.util.BoundingBox
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.overlay.Polyline

/** Insights home: arrival time + day-wise history list + Ask + learned routine. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InsightsScreen(deviceId: String, name: String?, onBack: () -> Unit, onPlans: () -> Unit,
                   onDay: (String) -> Unit = {}, onAsk: () -> Unit = {}) {
    var ins by remember { mutableStateOf<Insights?>(null) }
    var rows by remember { mutableStateOf<List<DayRow>>(emptyList()) }      // today + yesterday
    var custom by remember { mutableStateOf<List<DayRow>?>(null) }
    val scope = rememberCoroutineScope()
    var showHolidays by remember { mutableStateOf(false) }
    var childName by remember { mutableStateOf(name) }
    var msg by remember { mutableStateOf<String?>(null) }
    val who = childName ?: t("your child")

    LaunchedEffect(Unit) {
        if (childName == null) runCatching { Api.api.device(deviceId) }.onSuccess { childName = it.name }
        runCatching { Api.api.insights(deviceId) }.onSuccess { ins = it }.onFailure { msg = it.userMessage() }
    }
    LaunchedEffect(Unit) { runCatching { Api.api.days(deviceId) }.onSuccess { rows = it } }   // every plan
    var dev by remember { mutableStateOf<Device?>(null) }
    var brief by remember { mutableStateOf<Brief?>(null) }
    LaunchedEffect(Unit) {
        runCatching { Api.api.device(deviceId) }.onSuccess { dev = it }
        runCatching { Api.api.familyBrief() }.onSuccess { l -> brief = l.firstOrNull { it.device_id == deviceId } }
    }

    Scaffold(topBar = {
        TopAppBar(title = { Text(t("✨ Insights – {0}", childName ?: deviceId)) },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) } })
    }) { pad ->
        val i = ins
        LazyColumn(Modifier.padding(pad).fillMaxSize(), contentPadding = PaddingValues(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            msg?.let { item { Text(it, color = MaterialTheme.colorScheme.error) } }
            if (i == null) { item { CircularProgressIndicator() }; return@LazyColumn }
            if (i.locked) item {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFF3E5F5))) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(t("Arrival time, late / missed-place alerts, custom dates and “Ask about {0}” are in the Smart plan (₹299).", who),
                            Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
                        TextButton(onClick = onPlans) { Text(t("Upgrade")) }
                    }
                }
            }

            if (!i.locked && i.holiday_question && !i.holiday_today) item {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF8E1))) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(t("🏖 Is today a holiday for {0}?", who), fontWeight = FontWeight.Bold)
                        Text(t("{0} hasn't left at the usual time. If it's a holiday or sick day, routine alerts pause for today.", who))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = { scope.launch {
                                runCatching { Api.api.holidayAnswer(deviceId, HolidayAnswer(true)) }
                                ins = i.copy(holiday_today = true, holiday_question = false) } }) { Text(t("Yes, holiday")) }
                            OutlinedButton(onClick = { scope.launch {
                                runCatching { Api.api.holidayAnswer(deviceId, HolidayAnswer(false)) }
                                ins = i.copy(holiday_question = false) } }) { Text(t("No – keep alerts")) }
                        }
                    }
                }
            }
            if (!i.locked && i.holiday_today) item {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF8E1)), modifier = Modifier.fillMaxWidth()) {
                    Text(t("🏖 Holiday today – late / missed-place alerts are paused. SOS and safety alerts still work."),
                        Modifier.padding(14.dp))
                }
            }

            if (!i.locked) i.battery?.takeIf { it.hours_left != null && it.hours_left < 8 }?.let { b ->
                item {
                    Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF3E0)), modifier = Modifier.fillMaxWidth()) {
                        Text("🔋 ${b.text}", Modifier.padding(14.dp))
                    }
                }
            }
            // "now" card: same at-a-glance facts as the family screen (+ the learned arrival estimate)
            val d0 = dev
            if (d0 != null && brief != null) item {
                ElevatedCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(top = 16.dp)) {
                        Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(t("Right now"), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                            Text(briefMain(d0, brief), style = MaterialTheme.typography.titleMedium)
                            briefDetail(d0, brief)?.let { Text(it, color = Color(0xFF5F6368)) }
                            if (!i.locked) i.eta?.text?.takeIf { brief?.state == "moving" }?.let {
                                Text("🏠 $it", style = MaterialTheme.typography.bodyMedium)
                            }
                        }
                        Spacer(Modifier.height(12.dp))
                        BriefNotes(brief)
                    }
                }
            } else if (!i.locked) i.eta?.let { e ->
                item {
                    Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFE3F2FD)), modifier = Modifier.fillMaxWidth()) {
                        Text("🏠 ${e.text}", Modifier.padding(16.dp), fontWeight = FontWeight.Bold)
                    }
                }
            }

            if (!i.locked) item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    // week report / routine are answered by the AI ("How was babai's week?"), holidays are in Child setup
                    Button(onClick = onAsk, modifier = Modifier.fillMaxWidth().height(52.dp)) {
                        Icon(Icons.Default.AutoAwesome, null); Spacer(Modifier.width(8.dp)); Text(t("Ask about {0}", who))
                    }
                }
            }

            item {
                Text(t("History"), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(top = 6.dp))
            }
            if (!i.locked) item {
                LaunchedEffect(Unit) {
                    if (custom == null) {
                        val today = java.time.LocalDate.now(java.time.ZoneId.of("Asia/Kolkata"))
                        runCatching { Api.api.days(deviceId, today.minusDays(29).toString(), today.toString()) }
                            .onSuccess { custom = it }.onFailure { custom = emptyList(); msg = it.userMessage() }
                    }
                }
                val c = custom
                if (c == null) Text(t("Loading…"), color = Color.Gray) else HistoryCalendar(c, onDay)
            }
            // Basic plan: today + yesterday only (30-day calendar is in Smart)
            val shown = if (i.locked) rows.take(2) else emptyList()
            if (i.locked && rows.isEmpty()) item { Text(t("Loading…"), color = Color.Gray) }
            items(shown, key = { it.date }) { r ->
                Card(Modifier.fillMaxWidth().clickable { onDay(r.date) },
                    colors = CardDefaults.cardColors(containerColor = when (r.status) {
                        "attention" -> Color(0xFFFFF3E0); "normal" -> Color(0xFFE8F5E9); else -> MaterialTheme.colorScheme.surfaceVariant })) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(r.label, fontWeight = FontWeight.Bold)
                            Text(when (r.status) { "attention" -> "⚠️ ${r.line}"; "normal" -> "✅ ${r.line}"; else -> r.line } +
                                (if (r.status != "nodata") " · ${r.km} km" else ""))
                            if (r.places.isNotEmpty()) Text(r.places.joinToString(" → "), color = Color.Gray,
                                style = MaterialTheme.typography.bodySmall)
                        }
                        Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, t("Open"))
                    }
                }
            }
        }
    }

    if (showHolidays) HolidaysDialog(deviceId, who, onDone = { changed ->
        showHolidays = false
        if (changed) scope.launch { runCatching { Api.api.insights(deviceId) }.onSuccess { ins = it } }
    })

}

/** Holidays / vacations: routine alerts pause; holidays are not used for learning. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HolidaysDialog(deviceId: String, who: String, onDone: (Boolean) -> Unit) {
    val scope = rememberCoroutineScope()
    var list by remember { mutableStateOf<List<HolidayItem>?>(null) }
    var all by remember { mutableStateOf(true) }
    var pick by remember { mutableStateOf(false) }
    var changed by remember { mutableStateOf(false) }
    var err by remember { mutableStateOf<String?>(null) }
    var publicOn by remember { mutableStateOf(true) }
    LaunchedEffect(Unit) { runCatching { Api.api.setup(deviceId) }.onSuccess { publicOn = it.public_holidays } }
    val today = java.time.LocalDate.now(java.time.ZoneId.of("Asia/Kolkata")).toString()
    LaunchedEffect(Unit) { runCatching { Api.api.holidays(deviceId) }.onSuccess { list = it } }
    fun add(a: String, b: String?, note: String?) = scope.launch {
        runCatching { Api.api.addHolidays(deviceId, HolidayReq(a, b, note, all)) }
            .onSuccess { list = it; changed = true; err = null }.onFailure { err = it.userMessage() }
    }

    AlertDialog(onDismissRequest = { onDone(changed) }, title = { Text(t("🏖 Holidays")) },
        text = {
            Column(Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(t("On holidays, late / didn't-leave / missed-place alerts pause and the day is not used for learning.") + " " +
                    t("SOS, safe zones and unusual-route alerts keep working."), style = MaterialTheme.typography.bodySmall)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(all, { all = it }); Text(t("Apply to all my children"))
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(t("🇮🇳 Pause on public holidays (Diwali, Holi, 15 Aug…)"), Modifier.weight(1f))
                    Switch(publicOn, { on ->
                        publicOn = on
                        scope.launch {
                            runCatching { Api.api.saveSetup(deviceId, SetupReq(public_holidays = on)) }
                            runCatching { Api.api.holidays(deviceId) }.onSuccess { list = it; changed = true }
                        }
                    })
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { add(today, null, "Holiday") }) { Text(t("Today")) }
                    OutlinedButton(onClick = { pick = true }) { Text(t("Vacation dates")) }
                }
                err?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                Text(t("Upcoming"), fontWeight = FontWeight.Bold)
                val l = list
                if (l == null) Text(t("Loading…")) else if (l.isEmpty()) Text(t("No holidays set"), color = Color.Gray)
                l?.forEach { h ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text((if (h.public) "🇮🇳 " else "🏖 ") + h.day + (h.note?.let { " · $it" } ?: ""), Modifier.weight(1f))
                        if (!h.public) IconButton(onClick = { scope.launch {
                            runCatching { Api.api.deleteHoliday(deviceId, h.day) }.onSuccess { list = it; changed = true } } }) {
                            Icon(androidx.compose.material.icons.Icons.Default.Close, t("Remove"))
                        }
                    }
                }
            }
        }, confirmButton = { TextButton(onClick = { onDone(changed) }) { Text(t("Done")) } })

    if (pick) {
        val state = rememberDateRangePickerState()
        DatePickerDialog(onDismissRequest = { pick = false },
            confirmButton = {
                TextButton(enabled = state.selectedStartDateMillis != null, onClick = {
                    val fmt = { ms: Long -> java.time.Instant.ofEpochMilli(ms).atZone(java.time.ZoneOffset.UTC).toLocalDate().toString() }
                    add(fmt(state.selectedStartDateMillis!!), state.selectedEndDateMillis?.let(fmt), "Vacation")
                    pick = false
                }) { Text(t("Save")) }
            },
            dismissButton = { TextButton(onClick = { pick = false }) { Text(t("Cancel")) } }) {
            DateRangePicker(state, Modifier.height(480.dp), title = { Text(t("Vacation for {0}", who), Modifier.padding(16.dp)) })
        }
    }
}

/** Last 30 days as a month-style calendar. Green = normal, orange = SOS/alert, grey = no data. Tap a day. */
@Composable
fun HistoryCalendar(rows: List<DayRow>, onDay: (String) -> Unit) {
    val byDate = rows.associateBy { it.date }
    val today = java.time.LocalDate.now(java.time.ZoneId.of("Asia/Kolkata"))
    val first = today.minusDays(29)
    val gridStart = first.minusDays((first.dayOfWeek.value - 1).toLong())       // Monday of first week
    val weeks = ((java.time.temporal.ChronoUnit.DAYS.between(gridStart, today) / 7) + 1).toInt()
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("${first.format(java.time.format.DateTimeFormatter.ofPattern("d MMM"))} – " +
                today.format(java.time.format.DateTimeFormatter.ofPattern("d MMM yyyy")), fontWeight = FontWeight.Bold)
            Row { when (com.selfxtrack.app.i18n.I18n.lang) {
                "hi" -> listOf("सो", "मं", "बु", "गु", "शु", "श", "र")
                "bn" -> listOf("সো", "ম", "বু", "বৃ", "শু", "শ", "র")
                else -> listOf("M", "T", "W", "T", "F", "S", "S")
            }.forEach {
                Text(it, Modifier.weight(1f), textAlign = androidx.compose.ui.text.style.TextAlign.Center, color = Color.Gray) } }
            for (w in 0 until weeks) {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    for (d in 0 until 7) {
                        val date = gridStart.plusDays((w * 7 + d).toLong())
                        val inRange = !date.isBefore(first) && !date.isAfter(today)
                        val r = byDate[date.toString()]
                        val bg = when {
                            !inRange -> Color.Transparent
                            r?.status == "attention" -> Color(0xFFFFCC80)
                            r?.status == "normal" -> Color(0xFFA5D6A7)
                            else -> Color(0xFFEEEEEE)
                        }
                        Box(Modifier.weight(1f).aspectRatio(1f)
                            .background(bg, androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
                            .then(if (date == today) Modifier.border(2.dp, MaterialTheme.colorScheme.primary,
                                androidx.compose.foundation.shape.RoundedCornerShape(8.dp)) else Modifier)
                            .clickable(enabled = inRange) { onDay(date.toString()) },
                            contentAlignment = Alignment.Center) {
                            if (inRange) Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text("${date.dayOfMonth}", fontWeight = if (date == today) FontWeight.Bold else FontWeight.Normal)
                                if (r?.status == "attention") Text("⚠️", style = MaterialTheme.typography.labelSmall)
                            }
                        }
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.padding(top = 4.dp)) {
                listOf(Color(0xFFA5D6A7) to t("Normal"), Color(0xFFFFCC80) to t("SOS / alert"), Color(0xFFEEEEEE) to t("No data")).forEach { (c, l) ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(12.dp).background(c, androidx.compose.foundation.shape.RoundedCornerShape(3.dp)))
                        Text(" $l", style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
            Text(t("Tap a day to see its full history."), color = Color.Gray, style = MaterialTheme.typography.bodySmall)
        }
    }
}

/** Full history of one day: map of the route + timeline. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DayDetailScreen(deviceId: String, date: String, onBack: () -> Unit) {
    val ctx = LocalContext.current
    var d by remember { mutableStateOf<DayDetail?>(null) }
    var msg by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { runCatching { Api.api.day(deviceId, date) }.onSuccess { d = it }.onFailure { msg = it.userMessage() } }
    val mapView = remember { newMapView(ctx) }

    Scaffold(topBar = {
        TopAppBar(title = { Text(date) },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) } })
    }) { pad ->
        val x = d
        LazyColumn(Modifier.padding(pad).fillMaxSize(), contentPadding = PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            msg?.let { item { Text(it, color = MaterialTheme.colorScheme.error) } }
            if (x == null) { item { CircularProgressIndicator() }; return@LazyColumn }
            item { Text(x.summary, fontWeight = FontWeight.Bold) }
            item {
                Text(t("{0} to {1} · {2} km · max {3} km/h", x.first ?: "–", x.last ?: "–", x.distance_km, x.max_speed_kmh.toInt()) +
                    (x.min_battery?.let { t(" · battery low {0}%", it) } ?: ""), color = Color.Gray)
            }
            if (x.path.size == 1) item { Text(t("Only one location report this day."), color = Color.Gray) }
            if (x.path.size > 1) item {
                AndroidView({ mapView }, Modifier.fillMaxWidth().height(260.dp)) { map ->
                    map.overlays.clear()
                    val pts = x.path.map { GeoPoint(it.lat, it.lon) }
                    map.overlays.add(Polyline().apply { setPoints(pts); outlinePaint.color = 0xFF2E75B6.toInt() })
                    map.post { runCatching { map.zoomToBoundingBox(BoundingBox.fromGeoPoints(pts).increaseByScale(1.3f), false) } }
                    map.invalidate()
                }
            }
            item { Text(t("Timeline"), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium) }
            if (x.reports == 0) item {
                Text(t("No location reports on this day – the tracker was off, not charged or not linked yet."), color = Color.Gray)
            } else if (x.timeline.isEmpty()) item { Text(t("No stops or trips recorded."), color = Color.Gray) }
            items(x.timeline) { t ->
                Row(verticalAlignment = Alignment.Top) {
                    Text(t.time ?: "", Modifier.width(52.dp), fontWeight = FontWeight.Bold)
                    Text(when (t.kind) { "stay" -> "📍"; "travel" -> "🚶"; "sos" -> "🚨"; "bus" -> "🚌"; else -> "⚠️" }, Modifier.width(28.dp))
                    Column(Modifier.weight(1f)) {
                        Text(t.title, fontWeight = FontWeight.SemiBold,
                            color = if (t.kind == "sos") Color(0xFFC62828) else Color.Unspecified)
                        Text(t.text, color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                    }
                }
                HorizontalDivider(Modifier.padding(top = 6.dp))
            }
        }
    }
}

/** Chat with the assistant (answers only from tracker data). */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun AskScreen(deviceId: String, startLang: AppLang, onBack: () -> Unit, onLanguage: () -> Unit) {
    var lang by remember { mutableStateOf(startLang) }
    val scope = rememberCoroutineScope()
    var question by remember { mutableStateOf("") }
    var chat by remember { mutableStateOf(listOf<Pair<String, String>>()) }
    var tags by remember { mutableStateOf(listOf<String>()) }
    var status by remember { mutableStateOf<AiStatus?>(null) }
    LaunchedEffect(Unit) { runCatching { Api.api.aiStatus() }.onSuccess { status = it } }
    var busy by remember { mutableStateOf(false) }
    var who by remember { mutableStateOf(t("your child")) }
    LaunchedEffect(Unit) { runCatching { Api.api.device(deviceId) }.onSuccess { who = it.name ?: who } }
    val speaker = rememberSpeaker()
    // Read answers aloud – on by default since voice is the main way to ask.
    var readAloud by remember { mutableStateOf(true) }

    fun send(q: String, spoken: Boolean = false) {
        if (q.length < 3 || busy) return
        question = ""; busy = true; speaker.stop()
        scope.launch {
            val hist = chat.takeLast(3).flatMap { (uq, ua) -> listOf(ChatTurn("user", uq), ChatTurn("assistant", ua)) }
            val r = runCatching { Api.api.ask(deviceId, AskReq(q, hist, lang.code)) }
            val a = r.getOrNull()?.answer ?: r.exceptionOrNull()?.userMessage() ?: t("Error")
            val tag = r.getOrNull()?.let { x -> when (x.engine) {
                "guardrail" -> t("🛡 Safety rule")
                "local" -> t("⚙️ Built-in answer (no AI model)")
                else -> t("✨ AI model · {0}", x.model ?: x.engine)
            } } ?: ""
            chat = chat + (q to a); tags = tags + tag; busy = false
            if (readAloud || spoken) speaker.say(a, lang)
        }
    }
    val listen = rememberVoiceInput(lang) { send(it, spoken = true) }

    Scaffold(topBar = {
        TopAppBar(title = { Text(t("💬 Ask about {0}", who)) },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) } },
            actions = {
                AiLangPicker(lang) { lang = it; speaker.stop() }          // change the AI language here
                IconButton(onClick = { readAloud = !readAloud; if (!readAloud) speaker.stop() }) {
                    Icon(if (readAloud) Icons.AutoMirrored.Filled.VolumeUp else Icons.AutoMirrored.Filled.VolumeOff,
                        if (readAloud) t("Read answers aloud: on") else t("Read answers aloud: off"))
                }
            })
    }) { pad ->
        Column(Modifier.padding(pad).fillMaxSize().imePadding()) {
            LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp),
                reverseLayout = true) {
                items(chat.indices.reversed().toList()) { idx -> val (q, a) = chat[idx]
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFE3F2FD)), modifier = Modifier.align(Alignment.End)) {
                            Text(q, Modifier.padding(10.dp))
                        }
                        // Tap an answer to hear it again.
                        Card(onClick = { speaker.say(a, lang) }) { Text(a, Modifier.padding(10.dp)) }
                        tags.getOrNull(idx)?.takeIf { it.isNotEmpty() }?.let {
                            Text(it, color = Color.Gray, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
                if (chat.isEmpty()) item {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        ElevatedCard(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.Default.AutoAwesome, null, tint = MaterialTheme.colorScheme.primary)
                                    Spacer(Modifier.width(8.dp))
                                    Text(t("Ask anything about {0}", who), style = MaterialTheme.typography.titleMedium)
                                }
                                Text(t("Answers come only from {0}'s tracker data.", who), color = Color(0xFF5F6368))
                                status?.takeIf { it.engine == "local" || it.reachable != true }?.let { st ->
                                    Text(if (st.engine == "local") t("⚙️ AI model: not connected – built-in answers")
                                         else t("⚠️ AI model not reachable – using built-in answers"),
                                        style = MaterialTheme.typography.bodySmall, color = Color(0xFFE65100))
                                }
                            }
                        }
                        Text(t("Try asking"), style = MaterialTheme.typography.labelLarge, color = Color(0xFF5F6368))
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            listOf(t("Where is {0} now?", who), t("Is {0} safe now?", who), t("When will {0} come home?", who),
                                t("How was {0}'s day?", who), t("How was {0}'s week?", who), t("What is {0}'s usual routine?", who))
                                .forEach { s -> SuggestionChip(onClick = { send(s) }, label = { Text(s) },
                                    colors = SuggestionChipDefaults.suggestionChipColors(containerColor = Color.White)) }
                        }
                    }
                }
            }
            Row(Modifier.padding(8.dp).navigationBarsPadding(), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(question, { question = it }, Modifier.weight(1f), placeholder = { Text(t("Type or tap 🎤")) })
                if (question.isNotBlank()) {
                    IconButton(enabled = question.length > 2 && !busy, onClick = { send(question) }) {
                        if (busy) CircularProgressIndicator(Modifier.size(20.dp)) else Icon(Icons.AutoMirrored.Filled.Send, t("Ask"))
                    }
                } else {
                    Spacer(Modifier.width(8.dp))
                    FloatingActionButton(onClick = { when { busy -> {}; speaker.speaking -> speaker.stop(); else -> listen() } }) {
                        when {
                            busy -> CircularProgressIndicator(Modifier.size(24.dp))
                            speaker.speaking -> Icon(Icons.Filled.Stop, t("Stop speaking"))
                            else -> Icon(Icons.Filled.Mic, t("Ask by voice"))
                        }
                    }
                }
            }
        }
    }
}
