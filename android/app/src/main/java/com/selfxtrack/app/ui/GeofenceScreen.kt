package com.selfxtrack.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.GpsFixed
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.Geofence
import com.selfxtrack.app.data.userMessage
import com.selfxtrack.app.i18n.t
import kotlinx.coroutines.launch
import org.osmdroid.util.GeoPoint

/** Safe zones: move the map so the + is on the place (home / school / tuition), choose radius, add. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GeofenceScreen(deviceId: String, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var zones by remember { mutableStateOf<List<Geofence>>(emptyList()) }
    var name by remember { mutableStateOf("") }
    var radius by remember { mutableFloatStateOf(150f) }
    var msg by remember { mutableStateOf<String?>(null) }
    var centered by remember { mutableStateOf(false) }
    val map = remember { newMapView(ctx) }

    suspend fun load() {
        runCatching { Api.api.geofences(deviceId) }.onSuccess { zones = it }.onFailure { msg = it.userMessage() }
        if (!centered) runCatching { Api.api.device(deviceId) }.onSuccess { d ->
            if (d.last_lat != null && d.last_lon != null) { map.controller.setCenter(GeoPoint(d.last_lat, d.last_lon)); centered = true }
        }
    }
    LaunchedEffect(Unit) { load() }

    Scaffold(topBar = {
        TopAppBar(title = { Text(t("Safe zones")) },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) } })
    }) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            Box(Modifier.weight(1f).fillMaxWidth()) {
                AndroidView({ map }, Modifier.fillMaxSize()) { m ->
                    m.overlays.clear(); zones.forEach { m.overlays.add(geofenceCircle(it)) }; m.invalidate()
                }
                Icon(Icons.Default.Add, t("Centre"), Modifier.align(Alignment.Center).size(36.dp), tint = Color(0xFFC62828))
            }
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(t("Move the map so the red + is on the place, then add it."))
                OutlinedTextField(name, { name = it }, label = { Text(t("Name (Home, School, Tuition…)")) }, modifier = Modifier.fillMaxWidth())
                Text(t("Radius: {0} m", radius.toInt()))
                Slider(radius, { radius = it }, valueRange = 50f..1000f, steps = 18)
                Button(enabled = name.isNotBlank(), modifier = Modifier.fillMaxWidth(), onClick = {
                    val c = map.mapCenter
                    scope.launch {
                        runCatching { Api.api.addGeofence(deviceId, Geofence(name = name.trim(), lat = c.latitude, lon = c.longitude, radius_m = radius.toInt())) }
                            .onSuccess { name = ""; msg = t("Safe zone added. You'll be alerted on arrival and departure."); load() }
                            .onFailure { msg = it.userMessage() }
                    }
                }) { Icon(Icons.Default.GpsFixed, null); Text("  " + t("Add safe zone here")) }
                msg?.let { Text(it, color = MaterialTheme.colorScheme.secondary) }
            }
            LazyColumn(Modifier.heightIn(max = 180.dp)) {
                items(zones, key = { it.id }) { z ->
                    ListItem(headlineContent = { Text(z.name) },
                        supportingContent = { Text("${z.radius_m} m · " + when (z.inside) { true -> t("inside now"); false -> t("outside now"); null -> t("waiting for location") }) },
                        trailingContent = {
                            IconButton(onClick = { scope.launch { runCatching { Api.api.deleteGeofence(deviceId, z.id) }; load() } }) {
                                Icon(Icons.Default.Delete, t("Delete"))
                            }
                        })
                }
            }
        }
    }
}
