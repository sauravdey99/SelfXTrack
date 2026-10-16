package com.selfxtrack.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.StaffTrack
import com.selfxtrack.app.data.userMessage
import com.selfxtrack.app.i18n.t
import kotlinx.coroutines.delay
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polyline

/** School staff live tracking – works only while the student's SOS is active. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StaffTrackScreen(sosId: Int, onBack: () -> Unit) {
    val ctx = LocalContext.current
    var track by remember { mutableStateOf<StaffTrack?>(null) }
    var msg by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        while (true) {
            runCatching { Api.api.staffTrack(sosId) }.onSuccess { track = it; msg = null }.onFailure { msg = it.userMessage() }
            delay(10_000)
        }
    }
    val mapView = remember { newMapView(ctx) }
    Scaffold(topBar = {
        TopAppBar(title = { Text(t("🚨 {0} – live", track?.name ?: t("Student"))) },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) } })
    }) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            msg?.let { Text(it + " " + t("(tracking stops when the SOS ends)"), Modifier.padding(12.dp), color = Color.Gray) }
            AndroidView({ mapView }, Modifier.weight(1f).fillMaxWidth()) { map ->
                map.overlays.clear()
                track?.let { d ->
                    val pts = d.trail.map { GeoPoint(it.lat, it.lon) }
                    if (pts.size > 1) map.overlays.add(Polyline().apply { setPoints(pts); outlinePaint.color = 0xFFC62828.toInt() })
                    if (d.lat != null && d.lon != null) {
                        val p = GeoPoint(d.lat, d.lon)
                        map.overlays.add(Marker(map).apply { position = p; title = d.name; setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM) })
                        map.controller.setCenter(p)
                    }
                }
                map.invalidate()
            }
            track?.let { d ->
                Text(t("Updated {0} · ±{1} m · battery {2}%", ago(d.last_seen), d.accuracy_m?.toInt() ?: "?", d.battery ?: "–") +
                    (d.speed_kmh?.let { " · " + t("{0} km/h", it.toInt()) } ?: ""), Modifier.padding(12.dp))
                Row(Modifier.padding(horizontal = 12.dp, vertical = 4.dp).navigationBarsPadding(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { ctx.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:112"))) },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFC62828))) { Text(t("Call 112")) }
                    OutlinedButton(enabled = d.lat != null, onClick = {
                        ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("google.navigation:q=${d.lat},${d.lon}")))
                    }) { Text(t("Navigate")) }
                }
            }
        }
    }
}
