package com.selfxtrack.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.selfxtrack.app.data.*
import com.selfxtrack.app.i18n.t
import com.selfxtrack.app.live.LiveEvents
import kotlinx.coroutines.launch
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polyline

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MapScreen(deviceId: String, onBack: () -> Unit, onSos: (Int) -> Unit, onZones: (String) -> Unit, onSetup: (String) -> Unit, onInsights: (String) -> Unit) {
    val ctx = LocalContext.current
    var device by remember { mutableStateOf<Device?>(null) }
    var trail by remember { mutableStateOf<List<Point>>(emptyList()) }
    var zones by remember { mutableStateOf<List<Geofence>>(emptyList()) }
    var todayOnly by remember { mutableStateOf(true) }        // false = nothing today yet -> last 24 h shown
    var dialog by remember { mutableStateOf<String?>(null) }   // share / school / live
    var msg by remember { mutableStateOf<String?>(null) }
    var follow by remember { mutableStateOf(true) }
    var brief by remember { mutableStateOf<Brief?>(null) }
    val scope = rememberCoroutineScope()

    suspend fun load() {
        runCatching {
            device = Api.api.device(deviceId); zones = Api.api.geofences(deviceId)
            // the live map shows today's path; older days are in Insights -> History
            val today = Api.api.history(deviceId, today = true)
            todayOnly = today.size > 1
            trail = if (todayOnly) today else Api.api.history(deviceId, 24)
            runCatching { Api.api.familyBrief() }.onSuccess { l -> brief = l.firstOrNull { it.device_id == deviceId } }
        }.onFailure { msg = it.userMessage() }
    }
    LaunchedEffect(Unit) { load() }
    LaunchedEffect(Unit) { LiveEvents.events.collect { e -> if (e.optString("device_id") == deviceId) load() } }

    val mapView = remember { newMapView(ctx) }

    Scaffold(topBar = {
        TopAppBar(title = { Text(device?.name ?: deviceId) },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) } },
            actions = {
                IconButton(onClick = { onInsights(deviceId) }) { Icon(Icons.Default.AutoAwesome, t("Insights")) }
                IconButton(onClick = { onZones(deviceId) }) { Icon(Icons.Default.HomeWork, t("Safe zones")) }
                IconButton(onClick = { dialog = "live" }) { Icon(Icons.Default.Link, t("Live link")) }
                IconButton(onClick = { onSetup(deviceId) }) { Icon(Icons.Default.Settings, t("Child setup")) }
            })
    }) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            device?.active_sos?.let { sid ->
                Button(onClick = { onSos(sid) }, colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFC62828)),
                    modifier = Modifier.fillMaxWidth().padding(8.dp)) { Text(t("🚨 SOS ACTIVE – open emergency screen")) }
            }
            // clipToBounds: the map view would otherwise draw over the status row below it
            // follows the child until the parent drags / pinches the map; then a "back to child" button appears
            Box(Modifier.weight(1f).fillMaxWidth().clipToBounds().pointerInput(Unit) {
                awaitPointerEventScope {
                    while (true) {
                        val e = awaitPointerEvent(PointerEventPass.Initial)
                        if (e.changes.any { it.pressed && it.positionChange() != Offset.Zero }) follow = false
                    }
                }
            }) {
            AndroidView({ mapView }, Modifier.fillMaxSize()) { map ->
                map.overlays.clear()
                zones.forEach { map.overlays.add(geofenceCircle(it)) }
                val pts = trail.map { GeoPoint(it.lat, it.lon) }
                if (pts.size > 1) map.overlays.add(Polyline().apply { setPoints(pts); outlinePaint.color = 0xFF2E75B6.toInt() })
                device?.let { d ->
                    if (d.last_lat != null && d.last_lon != null) {
                        val p = GeoPoint(d.last_lat, d.last_lon)
                        map.overlays.add(Marker(map).apply {
                            position = p; title = d.name; snippet = t("Last seen {0} · ±{1} m", ago(d.last_seen), d.last_accuracy?.toInt() ?: "?")
                            setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                        })
                        // first time / far away: jump; small moves: glide smoothly
                        if (follow) { if (p.distanceToAsDouble(map.mapCenter) > 2000) map.controller.setCenter(p) else map.controller.animateTo(p) }
                    }
                }
                map.invalidate()
            }
            if (trail.size > 1) Surface(color = Color.White.copy(alpha = 0.85f), shape = MaterialTheme.shapes.small,
                modifier = Modifier.align(Alignment.TopStart).padding(8.dp)) {
                Text(if (todayOnly) t("Today's path") else t("Last 24 hours"), Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
                    style = MaterialTheme.typography.labelMedium, color = Color(0xFF2E75B6))
            }
            if (!follow && device?.last_lat != null) SmallFloatingActionButton(onClick = { follow = true },
                modifier = Modifier.align(Alignment.BottomEnd).padding(12.dp)) {
                Icon(Icons.Default.MyLocation, t("Back to child"))
            }
            }
            // status card: where / since when / what's next (same facts as the family screen)
            device?.let { d ->
                ElevatedCard(Modifier.fillMaxWidth().padding(start = 12.dp, end = 12.dp, top = 10.dp)) {
                    Row(Modifier.padding(start = 16.dp, end = 10.dp, top = 12.dp, bottom = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(briefMain(d, brief), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                            briefDetail(d, brief)?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Color(0xFF5F6368)) }
                            Text((if (d.online) "● " + t("Online") else "○ " + t("Offline")) + " · " +
                                t("Updated {0} · Battery {1}%", ago(d.last_seen), d.battery ?: "–"),
                                style = MaterialTheme.typography.labelMedium,
                                color = if (d.online) Color(0xFF2E7D32) else Color.Gray)
                        }
                        FilledTonalButton(enabled = d.last_lat != null, contentPadding = PaddingValues(horizontal = 14.dp), onClick = {
                            ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("google.navigation:q=${d.last_lat},${d.last_lon}")))
                        }) { Icon(Icons.Default.Navigation, null, Modifier.size(18.dp)); Text(" " + t("Navigate")) }
                    }
                }
            }
            RouteAlertsBar(deviceId)
            Box(Modifier.padding(horizontal = 12.dp)) { EmergencyPanel(deviceId, device?.active_sos, onSosCreated = onSos) }
            msg?.let { Text(it, Modifier.padding(12.dp)) }
            Spacer(Modifier.navigationBarsPadding())
        }
    }

    when (dialog) {
        "live" -> LiveLinkDialog(deviceId, device?.name, forSos = false, onDone = { dialog = null; msg = it })
    }
}

/** One small "Pause route alerts" button -> dialog: just this trip, or any time from 15 min to 8 h.
 *  Only unusual-route alerts are paused; SOS and safety alerts always work. */
@Composable
private fun RouteAlertsBar(deviceId: String) {
    val scope = rememberCoroutineScope()
    var now by remember { mutableStateOf<NowInfo?>(null) }
    var err by remember { mutableStateOf<String?>(null) }
    var open by remember { mutableStateOf(false) }
    suspend fun load() { runCatching { Api.api.now(deviceId) }.onSuccess { now = it } }
    LaunchedEffect(Unit) { load() }
    LaunchedEffect(Unit) { LiveEvents.events.collect { e -> if (e.optString("device_id") == deviceId) load() } }
    val until = now?.route_paused_until
    Column(Modifier.padding(horizontal = 12.dp, vertical = 2.dp)) {
        if (until != null) {
            Surface(color = Color(0xFFFFF3E0), shape = MaterialTheme.shapes.medium, modifier = Modifier.fillMaxWidth()) {
                Row(Modifier.padding(start = 12.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Text((if (now?.route_paused_trip == true) t("⏸ Route alerts paused for this trip (until {0})", until)
                          else t("⏸ Route alerts paused until {0}", until)) + " · " + t("SOS still works"),
                        Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
                    TextButton(onClick = { scope.launch { runCatching { Api.api.routeResume(deviceId) }; load() } }) { Text(t("Resume")) }
                }
            }
        } else {
            AssistChip(onClick = { open = true }, label = { Text(t("⏸ Pause route alerts")) })
        }
        err?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error) }
    }
    if (open) PauseRouteDialog(now?.trip, onDismiss = { open = false }) { req ->
        open = false
        scope.launch { runCatching { Api.api.routeOk(deviceId, req) }.onSuccess { err = null; load() }.onFailure { err = it.userMessage() } }
    }
}

@Composable
private fun PauseRouteDialog(trip: CurrentTrip?, onDismiss: () -> Unit, onPause: (RouteOkReq) -> Unit) {
    // "this trip" only exists while the child is travelling – otherwise only a time can be chosen
    var tripOnly by remember { mutableStateOf(trip != null) }
    var minutes by remember { mutableFloatStateOf(60f) }          // 15 … 480, 15-min steps
    var learn by remember { mutableStateOf(false) }
    val m = (minutes / 15).toInt() * 15
    val end = java.time.LocalTime.now(java.time.ZoneId.of("Asia/Kolkata")).plusMinutes(m.toLong())
        .format(java.time.format.DateTimeFormatter.ofPattern("HH:mm"))
    val dur = if (m >= 60) (if (m % 60 == 0) t("{0} h", m / 60) else t("{0} h {1} min", m / 60, m % 60)) else t("{0} min", m)
    AlertDialog(onDismissRequest = onDismiss, title = { Text(t("Pause route alerts")) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(t("Only unusual-route alerts are paused. SOS, fall, offline and battery alerts always work."),
                    style = MaterialTheme.typography.bodySmall, color = Color.Gray)
                if (trip != null) {
                    Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        RadioButton(tripOnly, { tripOnly = true })
                        Column {
                            Text(t("Only the current trip"))
                            Text(listOfNotNull(
                                trip.started_at?.let { at -> t("Left {0} at {1}", trip.started_from ?: t("the last stop"), at) },
                                trip.heading_to?.let { t("heading to {0}", it) }).joinToString(", ") + " · " +
                                t("ends when the child reaches one of their places"),
                                style = MaterialTheme.typography.bodySmall, color = Color.Gray)
                        }
                    }
                    Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        RadioButton(!tripOnly, { tripOnly = false })
                        Text(t("For a time"))
                    }
                }
                if (!tripOnly) {
                    Text(t("Until {0} ({1})", end, dur), fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
                    Slider(minutes, { minutes = it }, valueRange = 15f..480f, steps = 30)
                }
                if (tripOnly) Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Checkbox(learn, { learn = it })
                    Text(t("This is a regular route – remember it"), style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        confirmButton = { TextButton(onClick = { onPause(if (tripOnly) RouteOkReq(learn = learn) else RouteOkReq(minutes = m)) }) {
            Text(t("Pause")) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(t("Cancel")) } })
}

@Composable
fun LiveLinkDialog(deviceId: String, name: String?, forSos: Boolean, onDone: (String?) -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var minutes by remember { mutableIntStateOf(if (forSos) 180 else 60) }
    AlertDialog(onDismissRequest = { onDone(null) }, title = { Text(t("Share live location link")) },
        text = {
            Column {
                Text((if (forSos) t("Anyone with the link can see {0}'s live location in a browser until it expires or the SOS is resolved.", name ?: t("the tracker"))
                    else t("Anyone with the link can see {0}'s live location in a browser until it expires.", name ?: t("the tracker"))) +
                    " " + t("Share only with people you trust."))
                Row(Modifier.padding(top = 8.dp)) {
                    listOf(30 to "30 min", 60 to "1 h", 180 to "3 h", 480 to "8 h").forEach { (m, l) ->
                        FilterChip(selected = minutes == m, onClick = { minutes = m }, label = { Text(l) }, modifier = Modifier.padding(end = 4.dp))
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { scope.launch { onDone(shareLiveLink(ctx, deviceId, name, minutes, forSos)) } }) { Text(t("Create & share")) }
        }, dismissButton = { TextButton(onClick = { onDone(null) }) { Text(t("Cancel")) } })
}
