package com.selfxtrack.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.selfxtrack.app.data.*
import com.selfxtrack.app.i18n.t
import kotlinx.coroutines.launch

private fun placeEmoji(kind: String?) = when (kind) {
    "home" -> "🏠"; "school" -> "🏫"; "class" -> "📚"; "activity" -> "🏅"; "family" -> "👪"; else -> "📍"
}

/** Main status line of a child card, e.g. "🏫 At School since 08:04" / "🚲 On the way to Home · ~16:25". */
fun briefMain(d: Device, b: Brief?): String = when {
    d.active_sos != null -> t("🚨 SOS ACTIVE – tap now")
    b == null || b.state == "unknown" -> if (d.online) t("Online · {0}", ago(d.last_seen)) else t("Offline · last seen {0}", ago(d.last_seen))
    b.state == "offline" -> t("Offline · last seen {0}", ago(d.last_seen))
    b.state == "never" -> t("No location yet")
    b.state == "at" && b.place != null -> placeEmoji(b.place_kind) + " " +
        (if (b.since != null && b.since_day == "today") t("At {0} since {1}", b.place, b.since) else t("At {0}", b.place))
    b.state == "moving" && b.trip != null -> (when (b.mode) { "cycling" -> "🚲"; "vehicle" -> "🚗"; else -> "🚶" }) + " " +
        (b.trip.heading_to?.let { h -> t("On the way to {0}", h) + (b.trip.eta_time?.let { " · ~$it" } ?: "") }
            ?: t("Left {0} at {1}", b.trip.started_from ?: t("the last stop"), b.trip.started_at ?: "–"))
    else -> "📍 " + (b.near?.let { t("Near {0}", it) }
        ?: b.nearest_place?.let { t("{0} m from {1}", it.m, it.name) } ?: t("Online · {0}", ago(d.last_seen)))
}

/** Second line: on time / until / what's next / battery / bus. */
fun briefDetail(d: Device, b: Brief?): String? {
    if (b == null || d.active_sos != null) return null
    if (b.state == "offline")              // where it was last seen is what a parent asks first
        return b.place?.let { t("last at {0}", it) } ?: b.near?.let { t("last near {0}", it) }
    val parts = listOfNotNull(
        when (b.arrival) { "on_time" -> t("on time ✓"); "late" -> t("{0} min late", b.late_min ?: 0); else -> null },
        b.until?.let { t("until {0}", it) },
        b.next?.let { n -> if (n.source == "routine") t("next: {0} ~{1}", n.place, n.at ?: n.leave ?: "")
                           else t("next: {0} at {1}", n.place, n.at ?: "") },
        b.on_bus?.let { t("🚌 on {0}", it) },
        if (b.battery_low == true && b.battery_until != null) t("🔋 runs out ~{0}", b.battery_until) else null)
    return parts.joinToString(" · ").ifBlank { null }
}

/** Small notes under a child card: alerts today, paused route alerts, holiday. */
@Composable
fun BriefNotes(b: Brief?) {
    if (b == null) return
    val notes = listOfNotNull(
        b.alerts_today?.takeIf { it > 0 }?.let { n -> Triple("⚠️", t("{0} alerts today · last {1}", n, b.last_alert?.time ?: ""), Color(0xFFE65100)) },
        b.route_alerts_paused_until?.let { Triple("⏸", t("⏸ Route alerts paused until {0}", it).removePrefix("⏸ "), Color(0xFF6D4C41)) },
        if (b.holiday == true) Triple("🏖", t("Holiday today"), Color(0xFF00796B)) else null)
    if (notes.isEmpty()) return
    Row(Modifier.padding(start = 16.dp, end = 16.dp, bottom = 12.dp).horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        notes.forEach { (icon, text, color) ->
            Surface(shape = RoundedCornerShape(10.dp), color = color.copy(alpha = 0.10f)) {
                Text("$icon $text", Modifier.padding(horizontal = 8.dp, vertical = 4.dp), color = color,
                    style = MaterialTheme.typography.labelMedium)
            }
        }
    }
}


/** "🌐 ಕನ್ನಡ ▾" – change the AI language (voice + answers) right where the parent asks. Saved for the whole app. */
@Composable
fun AiLangPicker(current: AppLang, onPick: (AppLang) -> Unit) {
    val scope = rememberCoroutineScope()
    var open by remember { mutableStateOf(false) }
    Box {
        TextButton(onClick = { open = true }, contentPadding = PaddingValues(horizontal = 10.dp)) {
            Icon(Icons.Default.Language, null, Modifier.size(18.dp)); Spacer(Modifier.width(4.dp))
            Text(current.native); Icon(Icons.Default.ArrowDropDown, t("AI language"))
        }
        DropdownMenu(open, { open = false }) {
            Text(t("AI language"), Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
                style = MaterialTheme.typography.labelMedium, color = Color(0xFF5F6368))
            LANGUAGES.forEach { l ->
                DropdownMenuItem(text = { Text(if (l.native == l.english) l.native else "${l.native}  ·  ${l.english}") },
                    trailingIcon = if (l.code == current.code) { { Icon(Icons.Default.Check, null) } } else null,
                    onClick = {
                        open = false; onPick(l)
                        scope.launch { Api.session.setLanguages(Api.session.appLang ?: "en", l.code) }
                    })
            }
        }
    }
}
