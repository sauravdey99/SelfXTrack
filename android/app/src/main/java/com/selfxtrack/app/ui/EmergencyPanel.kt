package com.selfxtrack.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.selfxtrack.app.data.*
import com.selfxtrack.app.i18n.t
import com.selfxtrack.app.live.LiveEvents
import kotlinx.coroutines.launch

/** "Emergency – School" / "Emergency – Group" buttons + live status (helpers coming, who viewed location). */
@Composable
fun EmergencyPanel(deviceId: String, sosId: Int?, onSosCreated: (Int) -> Unit = {}) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var status by remember { mutableStateOf<SosStatus?>(null) }
    var msg by remember { mutableStateOf<String?>(null) }
    var confirm by remember { mutableStateOf<String?>(null) }

    var now by remember { mutableStateOf<NowInfo?>(null) }
    suspend fun load() {
        sosId?.let { id -> runCatching { Api.api.sosStatus(id) }.onSuccess { status = it } }
        runCatching { Api.api.now(deviceId) }.onSuccess { now = it }
    }
    LaunchedEffect(sosId) { load() }
    LaunchedEffect(sosId) { LiveEvents.events.collect { load() } }

    val basic = status?.plan == "basic"
    val alerted = status?.alerted_to
    val schoolDone = if (alerted != null) "school" in alerted else status?.school_notified_at != null
    // the place the child should be at right now (swimming, tuition …) if it has people to alert
    val here = now?.place?.takeIf { it.kind != "school" && now?.people?.isNotEmpty() == true }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        here?.let { p ->
            val done = alerted?.contains("place:${p.id}") == true
            Button(modifier = Modifier.fillMaxWidth(), onClick = { confirm = "place" },
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFEF6C00))) {
                Text(if (done) t("📍 {0} alerted ✓", p.name) else t("📍 Alert people at {0}", p.name), fontSize = 13.sp)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(modifier = Modifier.weight(1f), onClick = { confirm = "school" },
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1F4E79))) {
                Text(if (schoolDone) t("🏫 School alerted ✓") else t("🏫 Emergency – School"), fontSize = 13.sp)
            }
            Button(modifier = Modifier.weight(1f), onClick = { confirm = "group" },
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF6A1B9A))) {
                Text(if (status?.group != null) t("👥 Group alerted ✓") else t("👥 Emergency – Group"), fontSize = 13.sp)
            }
        }
        if (basic) Text(t("School and Group help are on Smart / Guardian plans."), color = Color(0xFFB26A00), fontSize = 12.sp)
        status?.group?.let { g ->
            Text(t("👥 {0} nearby users alerted within {1} km · {2} coming", g.notified, g.radius_m / 1000.0, g.accepted), fontWeight = FontWeight.Bold)
        }
        status?.helpers?.forEach { h ->
            Row(Modifier.fillMaxWidth()) {
                Text("🙋 ${h.name}" + (h.distance_m?.let { " · " + t("{0} m away", it) } ?: ""), Modifier.weight(1f))
                h.phone?.let { p -> TextButton(onClick = { ctx.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$p"))) }) { Text(t("Call")) } }
            }
        }
        status?.access_log?.takeIf { it.isNotEmpty() }?.let { logs ->
            Text(t("Location viewed by: {0}", logs.map { "${it.name} (${it.kind})" }.distinct().take(6).joinToString(", ")),
                fontSize = 12.sp, color = Color.Gray)
        }
        msg?.let { Text(it, color = MaterialTheme.colorScheme.secondary) }
    }

    confirm?.let { target ->
        AlertDialog(onDismissRequest = { confirm = null },
            title = { Text(when (target) {
                "school" -> t("Alert the school?")
                "place" -> t("Alert people at {0}?", now?.place?.name ?: "")
                else -> t("Alert nearby SelfXTrack users?") }) },
            text = {
                Text(when (target) {
                    "school" -> t("School staff and teacher contacts will get an emergency alert with the live location.")
                    "place" -> t("{0} will get an emergency SMS with the live location.",
                        now?.people?.joinToString(", ") { it.name } ?: "")
                    else -> t("Everyone using SelfXTrack within 1 km (2 km if nobody responds in 2 minutes) will be asked to help.") + " " +
                        t("People who accept will see the live location until you mark the child safe.") })
            },
            confirmButton = {
                TextButton(onClick = {
                    confirm = null
                    scope.launch {
                        runCatching { Api.api.emergency(deviceId, EmergencyReq(target, if (target == "place") now?.place?.id else null)) }.onSuccess { r ->
                            msg = r.warning ?: when (target) {
                                "school" -> t("School alerted ({0} staff, {1} contacts).", r.staff ?: 0, r.contacts ?: 0)
                                "place" -> t("{0} alerted ({1} people).", now?.place?.name ?: "", r.people ?: 0)
                                else -> t("{0} nearby users alerted.", r.notified ?: 0) }
                            if (sosId == null) onSosCreated(r.sos_id) else load()
                        }.onFailure { msg = it.userMessage() }
                    }
                }) { Text(t("Send alert"), color = Color(0xFFC62828)) }
            }, dismissButton = { TextButton(onClick = { confirm = null }) { Text(t("Cancel")) } })
    }
}
