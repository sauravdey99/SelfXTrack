package com.selfxtrack.app.ui

import android.content.Context
import android.content.Intent
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.Geofence
import com.selfxtrack.app.data.ShareLinkReq
import com.selfxtrack.app.data.userMessage
import com.selfxtrack.app.i18n.t
import org.osmdroid.tileprovider.tilesource.XYTileSource
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Polygon
import java.time.Duration
import java.time.OffsetDateTime

fun ago(iso: String?): String {
    if (iso == null) return t("never")
    return runCatching {
        val ts = OffsetDateTime.parse(if (iso.endsWith("Z") || iso.contains('+')) iso else iso + "Z")
        val m = Duration.between(ts, OffsetDateTime.now()).toMinutes()
        when {
            m < 1 -> t("just now")
            m < 60 -> t("{0} min ago", m)
            m < 1440 -> t("{0} h ago", m / 60)
            else -> t("{0} d ago", m / 1440)
        }
    }.getOrDefault(iso)
}

/** Map view with OpenStreetMap tiles. */
fun newMapView(ctx: Context): MapView = MapView(ctx).apply {
    setTileSource(org.osmdroid.tileprovider.tilesource.TileSourceFactory.MAPNIK)   // OpenStreetMap, no API key
    setMultiTouchControls(true)
    controller.setZoom(16.0)
}

fun geofenceCircle(g: Geofence): Polygon = Polygon().apply {
    points = Polygon.pointsAsCircle(GeoPoint(g.lat, g.lon), g.radius_m.toDouble())
    fillPaint.color = 0x332E7D32
    outlinePaint.color = 0xFF2E7D32.toInt()
    outlinePaint.strokeWidth = 3f
    title = g.name
}

/** Creates a temporary live-location web link and opens the share sheet (WhatsApp, SMS...). */
suspend fun shareLiveLink(ctx: Context, deviceId: String, name: String?, minutes: Int, forSos: Boolean): String? =
    runCatching { Api.api.createLink(deviceId, ShareLinkReq(minutes, forSos)) }.fold(
        onSuccess = { link ->
            val text = (if (forSos) "🚨 SOS – " else "") +
                t("Live location of {0} (valid {1}): {2}", name ?: t("my child"),
                    if (minutes >= 60) t("{0} h", minutes / 60) else t("{0} min", minutes), link.url)
            ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain")
                .putExtra(Intent.EXTRA_TEXT, text), t("Share live location")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            null
        },
        onFailure = { it.userMessage() })


/** Confirm / Cancel dialog for important emergency actions. */
@androidx.compose.runtime.Composable
fun ConfirmDialog(title: String, text: String, confirm: String, danger: Boolean = false,
                  onConfirm: () -> Unit, onCancel: () -> Unit) {
    androidx.compose.material3.AlertDialog(onDismissRequest = onCancel,
        title = { androidx.compose.material3.Text(title) },
        text = { androidx.compose.material3.Text(text) },
        confirmButton = {
            androidx.compose.material3.Button(onClick = onConfirm,
                colors = androidx.compose.material3.ButtonDefaults.buttonColors(
                    containerColor = if (danger) androidx.compose.ui.graphics.Color(0xFFC62828)
                                     else androidx.compose.ui.graphics.Color(0xFF2E7D32))) {
                androidx.compose.material3.Text(confirm)
            }
        },
        dismissButton = { androidx.compose.material3.TextButton(onClick = onCancel) { androidx.compose.material3.Text(t("Cancel")) } })
}
