package com.selfxtrack.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.HelpDetail
import com.selfxtrack.app.data.userMessage
import com.selfxtrack.app.i18n.t
import com.selfxtrack.app.live.HelperLocation
import com.selfxtrack.app.live.LiveEvents
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Helper view of an "Emergency – Group" request. Level 1: distance only. Level 2 (after accepting): live location. */
@Composable
fun HelpScreen(helpId: Int, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var d by remember { mutableStateOf<HelpDetail?>(null) }
    var msg by remember { mutableStateOf<String?>(null) }

    suspend fun load() { runCatching { Api.api.help(helpId) }.onSuccess { d = it }.onFailure { msg = it.userMessage() } }
    LaunchedEffect(Unit) { HelperLocation.upload(ctx, precise = true); load() }
    LaunchedEffect(Unit) { LiveEvents.events.collect { load() } }
    // while helping: refresh + share my position with the family every 20 s
    LaunchedEffect(d?.status) {
        while (d?.status == "accepted" && d?.closed == false) { delay(20_000); HelperLocation.upload(ctx, precise = true); load() }
    }

    val red = Color(0xFFC62828)
    Column(Modifier.fillMaxSize().background(Color(0xFFFFF8E1)).verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        val h = d
        when {
            h == null -> Text(msg ?: t("Loading…"))
            h.closed -> {
                Text(t("✅ Child is safe"), fontSize = 26.sp, fontWeight = FontWeight.Bold, color = Color(0xFF2E7D32))
                Text(h.message ?: t("Thank you for being ready to help."))
            }
            h.status != "accepted" -> {
                Text(t("🆘 Help needed nearby"), fontSize = 26.sp, fontWeight = FontWeight.Bold, color = red)
                Text(t("A child about {0} m from you needs help.", h.distance_m ?: "?") + " " +
                    t("If you can safely help, tap “I can help” to see the live location.") + " " +
                    t("The family will see your name and position."))
                Button(onClick = { scope.launch { runCatching { Api.api.acceptHelp(helpId) }.onSuccess { d = it }.onFailure { msg = it.userMessage() } } },
                    colors = ButtonDefaults.buttonColors(containerColor = red), modifier = Modifier.fillMaxWidth().height(56.dp)) {
                    Text(t("🙋 I can help"), fontSize = 18.sp)
                }
                OutlinedButton(onClick = { scope.launch { runCatching { Api.api.declineHelp(helpId) }; onBack() } },
                    modifier = Modifier.fillMaxWidth()) { Text(t("I can't help now")) }
            }
            else -> {
                Text(t("🆘 You are helping {0}", h.name ?: t("a child")), fontSize = 22.sp, fontWeight = FontWeight.Bold, color = red)
                Text("⚠️ ${h.safety}", fontWeight = FontWeight.Bold)
                Text(t("Distance ≈ {0} m", h.distance_m ?: "?") + " · " + t("updated {0}", ago(h.last_seen)) + " · " + t("battery {0}%", h.battery ?: "–") +
                    (h.speed_kmh?.let { " · ${it.toInt()} km/h" } ?: "") + (h.heading_deg?.let { " · " + t("heading {0}°", it.toInt()) } ?: ""))
                Button(enabled = h.lat != null, modifier = Modifier.fillMaxWidth().height(52.dp), onClick = {
                    ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("google.navigation:q=${h.lat},${h.lon}")))
                }) { Text(t("Navigate to child")) }
                Button(onClick = { ctx.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:112"))) },
                    colors = ButtonDefaults.buttonColors(containerColor = red), modifier = Modifier.fillMaxWidth()) { Text(t("Call 112")) }
                h.family?.forEach { f ->
                    f.phone?.let { p ->
                        OutlinedButton(modifier = Modifier.fillMaxWidth(), onClick = {
                            ctx.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$p")))
                        }) { Text(t("Call family: {0}", f.name)) }
                    }
                }
            }
        }
        msg?.let { Text(it, color = red) }
        TextButton(onClick = onBack) { Text(t("Back")) }
    }
}
