package com.selfxtrack.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.Device
import com.selfxtrack.app.data.Sos
import com.selfxtrack.app.data.userMessage
import com.selfxtrack.app.i18n.t
import com.selfxtrack.app.live.LiveEvents
import kotlinx.coroutines.launch

/** Emergency screen opened from the SOS notification. */
@Composable
fun SosScreen(sosId: Int, onBack: () -> Unit) {
    val ctx = LocalContext.current
    var reportText by remember { mutableStateOf<String?>(null) }
    var confirm by remember { mutableStateOf<String?>(null) }
    var sos by remember { mutableStateOf<Sos?>(null) }
    var device by remember { mutableStateOf<Device?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var showLive by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    suspend fun load() {
        runCatching {
            sos = Api.api.activeSos(activeOnly = false).firstOrNull { it.id == sosId }
            sos?.device_id?.let { device = Api.api.device(it) }
        }.onFailure { error = it.userMessage() }
    }
    LaunchedEffect(Unit) { load() }
    LaunchedEffect(Unit) { LiveEvents.events.collect { load() } }

    val red = Color(0xFFC62828)
    val resolved = sos?.status == "resolved" || sos?.status == "cancelled"
    Column(Modifier.fillMaxSize().background(if (resolved) Color(0xFFE8F5E9) else Color(0xFFFFEBEE)).verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        val fall = sos?.source == "fall"
        Text(if (resolved) t("✅ Marked safe") else if (fall) t("🆘 POSSIBLE FALL") else t("🚨 SOS ALERT"), fontSize = 30.sp, fontWeight = FontWeight.Bold,
            color = if (resolved) Color(0xFF2E7D32) else red)
        Text(if (fall) t("{0} may have fallen {1} and did not cancel the alert.", sos?.device_name ?: t("Your family member"), ago(sos?.started_at))
             else t("{0} pressed the SOS button {1}.", sos?.device_name ?: t("Your child"), ago(sos?.started_at)), fontSize = 18.sp)
        val lat = device?.last_lat ?: sos?.lat
        val lon = device?.last_lon ?: sos?.lon
        Text(if (lat != null) t("Last location: {0}, {1} (updated {2})", "%.5f".format(lat), "%.5f".format(lon), ago(device?.last_seen))
             else t("Waiting for location…"))
        Text(t("Battery: {0}%", device?.battery ?: "–"))
        when {
            sos?.status == "active" -> Text(t("⏳ Nobody has responded yet – tap “I'm on it” if you are handling it."),
                color = Color(0xFFC62828), fontWeight = FontWeight.Bold)
            sos?.status == "acknowledged" -> Text(t("✅ {0} is on it", sos?.responder ?: t("Someone")) +
                (sos?.acknowledged_at?.let { " (" + t("since {0}", ago(it)) + ")" } ?: ""), color = Color(0xFF2E7D32), fontWeight = FontWeight.Bold)
            sos?.status == "resolved" -> Text(t("✅ Child marked safe"), color = Color(0xFF2E7D32), fontWeight = FontWeight.Bold)
        }

        Button(onClick = { ctx.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:112"))) },
            colors = ButtonDefaults.buttonColors(containerColor = red), modifier = Modifier.fillMaxWidth().height(56.dp)) {
            Icon(Icons.Default.Call, null); Text("  " + t("Call 112 (Emergency)"), fontSize = 18.sp)
        }
        OutlinedButton(enabled = lat != null, modifier = Modifier.fillMaxWidth().height(52.dp), onClick = {
            ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("google.navigation:q=$lat,$lon")))
        }) { Icon(Icons.Default.Navigation, null); Text("  " + t("Navigate to location")) }

        if (!resolved) {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                if (sos?.status == "active") Button(modifier = Modifier.weight(1f), onClick = { confirm = "ack" }) { Text(t("I'm on it")) }
                Button(modifier = Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2E7D32)),
                    onClick = { confirm = "safe" }) {
                    Text(t("Child is safe"))
                }
            }
            sos?.device_id?.let { EmergencyPanel(it, sosId) }
            OutlinedButton(onClick = {
                scope.launch {
                    runCatching { Api.api.report(sosId) }.onSuccess { reportText = it.text }.onFailure { error = it.userMessage() }
                }
            }, modifier = Modifier.fillMaxWidth()) { Text(t("📄 Incident report (for police / school)")) }
        }
        error?.let { Text(it, color = red) }
        when (confirm) {
            "ack" -> ConfirmDialog(t("I'm on it?"),
                t("The family and school will see that you are handling this SOS.") + " " +
                    t("The alarm stops on other phones and the automatic escalation to family / school is stopped.") + " " +
                    t("Only confirm if you are going to help now."),
                t("Confirm"), onConfirm = {
                    confirm = null
                    scope.launch { runCatching { Api.api.acknowledge(sosId) }.onFailure { error = it.userMessage() }; load() }
                }, onCancel = { confirm = null })
            "safe" -> ConfirmDialog(t("Is the child really safe?"),
                t("This ends the SOS for everyone: school and nearby helpers are told to stop and live links stop.") + " " +
                    t("Confirm only if you have seen or spoken to the child."),
                t("Yes, child is safe"), onConfirm = {
                    confirm = null
                    scope.launch { runCatching { Api.api.resolve(sosId) }.onFailure { error = it.userMessage() }; load() }
                }, onCancel = { confirm = null })
        }
        reportText?.let { rep ->
            AlertDialog(onDismissRequest = { reportText = null }, title = { Text(t("Incident report")) },
                text = { Text(rep, modifier = Modifier.verticalScroll(rememberScrollState())) },
                confirmButton = { TextButton(onClick = {
                    ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain")
                        .putExtra(Intent.EXTRA_TEXT, rep), t("Share report")))
                }) { Text(t("Share")) } },
                dismissButton = { TextButton(onClick = { reportText = null }) { Text(t("Close")) } })
        }
        if (showLive) sos?.device_id?.let { LiveLinkDialog(it, sos?.device_name, forSos = true, onDone = { m -> showLive = false; error = m }) }
        Spacer(Modifier.height(12.dp))
        TextButton(onClick = onBack, modifier = Modifier.align(Alignment.CenterHorizontally)) { Text(t("Back")) }
    }
}
