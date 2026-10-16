package com.selfxtrack.app.live

import android.app.Notification
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.selfxtrack.app.R
import com.selfxtrack.app.SelfXApp
import com.selfxtrack.app.i18n.t
import com.selfxtrack.app.ui.MainActivity

/** Builds all app notifications (used by the WebSocket service and Firebase push). */
object Notifier {
    private val shownSos = mutableSetOf<Int>()

    fun handle(ctx: Context, type: String, get: (String) -> String?) {
        val name = get("name") ?: t("Your child")
        when (type) {
            "sos" -> sos(ctx, get("sos_id")?.toIntOrNull() ?: 0, name, school = get("role") == "school", fall = get("reason") == "fall",
                by = get("by")?.takeIf { it.isNotBlank() }, place = get("place")?.takeIf { it.isNotBlank() })
            "bus" -> info(ctx, "bus${get("device_id")}", t("🚌 {0} – bus", name), get("text") ?: t("Bus update for {0}.", name))
            "sos_update" -> if (get("status") == "resolved")
                NotificationManagerCompat.from(ctx).cancel(1000 + (get("sos_id")?.toIntOrNull() ?: 0))
            "route_ok" -> {                       // someone in the family tapped "It's OK" / paused route alerts
                clearRoute(ctx, get("device_id") ?: "")
                info(ctx, "routeok${get("device_id")}", t("✅ Route alerts paused"), get("text") ?: "")
            }
            "ai_alert" -> {
                val title = when (get("kind")) { "risk" -> t("⚠️ Check on {0}?", name); "stop" -> t("📍 Unfamiliar stop"); "late" -> t("⏰ {0} is late", name)
                    "noleave" -> t("🕒 {0} hasn't left yet", name); "missed" -> t("❓ {0} missed a usual place", name)
                    "holiday_q" -> t("🏖 Holiday for {0} today?", name); "detour" -> t("↪️ {0} left the usual route", name)
                    "speed" -> t("🚗 {0} is moving fast", name); "linger" -> t("⏸ {0} stopped on the way", name)
                    "time" -> t("🌙 Usual road, unusual time"); "battery" -> t("🔋 {0}'s tracker will run out soon", name)
                    "weekly" -> t("📊 {0}'s week", name); "inactivity" -> t("🧓 Check on {0}", name); else -> t("🧭 Unusual route") }
                val text = get("text") ?: (t("Unusual activity for {0}.", name) + " " + t("Open the app to check."))
                val key = "ai${get("device_id")}${get("kind")}"
                if (get("kind") in ROUTE_KINDS) routeAlert(ctx, get("device_id") ?: "", key, title, text)
                else info(ctx, key, title, text)
            }
            "low_battery" -> info(ctx, "low${get("device_id")}", t("Low battery"),
                t("Tracker battery is {0}%.", get("bat") ?: get("battery") ?: t("low")) + " " + t("Please charge it."))
            "offline" -> info(ctx, "off${get("device_id")}", t("Tracker offline"), t("No update from {0}'s tracker for a while.", name))
            "online" -> info(ctx, "off${get("device_id")}", t("Back online"), t("{0}'s tracker is connected again.", name))
            "geofence_enter" -> info(ctx, "gf${get("device_id")}", t("✅ {0} reached {1}", name, get("geofence")), t("{0} arrived at {1}.", name, get("geofence")))
            "help_request" -> help(ctx, get("help_id")?.toIntOrNull() ?: 0, get("distance_m") ?: "?")
            "help_closed" -> NotificationManagerCompat.from(ctx).cancel(5000 + (get("help_id")?.toIntOrNull() ?: 0))
                .also { info(ctx, "help${get("help_id")}", t("✅ Child is safe"), t("Thank you – the family marked the child safe.")) }
            "helper_accepted" -> info(ctx, "ha${get("sos_id")}", t("🙋 Helper is coming"), t("{0} is going to help.", get("name")))
            "family_escalated" -> info(ctx, "fe${get("sos_id")}", t("👪 {0} raised an emergency", get("by") ?: t("Family")),
                t("{0} alerted school / nearby help for {1}.", get("by") ?: t("A family member"), name) + " " + t("Open the app to follow."))
            "school_escalated" -> info(ctx, "se${get("sos_id")}", t("🏫 School alerted"), t("School staff have been informed."))
            "group_started", "group_expanded" -> info(ctx, "gs${get("sos_id")}", t("👥 Group help requested"), t("Nearby SelfXTrack users are being alerted ({0} so far).", get("notified") ?: "0"))
            "family_request" -> info(ctx, "fam${get("device_id")}", t("👪 Family request"), t("A family member you invited joined SelfXTrack.") + " " + t("Open Child setup to accept."))
            "family_added" -> info(ctx, "famadd${get("device_id")}", t("👪 You were added"), t("You can now see the child's location and SOS alerts."))
            "staff_approved" -> info(ctx, "staff", t("School access approved"), t("You will now receive student SOS alerts."))
            "geofence_exit" -> info(ctx, "gf${get("device_id")}", t("{0} left {1}", name, get("geofence")), t("{0} has left {1}.", name, get("geofence")))
        }
    }

    fun sos(ctx: Context, sosId: Int, name: String, school: Boolean = false, fall: Boolean = false, by: String? = null,
            place: String? = null) {
        synchronized(shownSos) { if (!shownSos.add(sosId)) return }
        val intent = Intent(ctx, MainActivity::class.java)
            .putExtra(if (school) MainActivity.EXTRA_SCHOOL_SOS else MainActivity.EXTRA_SOS_ID, sosId)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val pi = PendingIntent.getActivity(ctx, sosId, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val title = if (fall) t("🆘 POSSIBLE FALL – {0}", name) else if (school) (if (place != null) t("🚨 Emergency at {0} – {1}", place, name) else t("🚨 Student emergency – {0}", name))
            else t("🚨 SOS ALERT")
        // School is alerted only when a parent pressed Emergency – School, or nobody in the family responded in time
        val text = if (fall) t("{0} may have fallen and did not cancel the alert.", name) + " " + t("Tap to see location.")
            else if (school) (if (by != null) t("{0} (parent) asked the school for help with {1}.", by, name)
                              else t("No one in {0}'s family has responded to the SOS yet.", name)) + " " + t("Tap for live location.")
            else t("{0} has pressed the SOS button.", name) + " " + t("Tap to see location.")
        val n = NotificationCompat.Builder(ctx, SelfXApp.CH_SOS)
            .setSmallIcon(R.drawable.ic_shield).setContentTitle(title).setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_MAX).setCategory(Notification.CATEGORY_ALARM)
            .setContentIntent(pi).setFullScreenIntent(pi, true).setOngoing(true).setAutoCancel(true).build()
        runCatching { NotificationManagerCompat.from(ctx).notify(1000 + sosId, n) }
    }

    fun help(ctx: Context, helpId: Int, distance: String) {
        val intent = Intent(ctx, MainActivity::class.java).putExtra(MainActivity.EXTRA_HELP_ID, helpId)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val pi = PendingIntent.getActivity(ctx, 5000 + helpId, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val text = t("A child needs help about {0} m from you.", distance) + " " + t("Tap if you can help.")
        val n = NotificationCompat.Builder(ctx, SelfXApp.CH_SOS)
            .setSmallIcon(R.drawable.ic_shield).setContentTitle(t("🆘 Help needed nearby")).setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_MAX).setCategory(Notification.CATEGORY_ALARM)
            .setContentIntent(pi).setAutoCancel(true).build()
        runCatching { NotificationManagerCompat.from(ctx).notify(5000 + helpId, n) }
    }

    /** Alerts a parent can silence with "It's OK" (never SOS, fall, offline, battery, schedules). */
    val ROUTE_KINDS = setOf("route", "detour", "stop", "linger", "time", "speed", "late", "missed")   // same as server ai.ROUTE_KINDS

    /** Route alert with two buttons: "It's OK" (this trip) and "Regular route" (learn it). Works with the app closed. */
    fun routeAlert(ctx: Context, deviceId: String, key: String, title: String, text: String) {
        val open = PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        fun action(learn: Boolean): PendingIntent = PendingIntent.getBroadcast(ctx, (deviceId + learn).hashCode(),
            Intent(ctx, RouteOkReceiver::class.java).putExtra("device_id", deviceId).putExtra("learn", learn),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val n = NotificationCompat.Builder(ctx, SelfXApp.CH_INFO)
            .setSmallIcon(R.drawable.ic_shield).setContentTitle(title).setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(open).setAutoCancel(true)
            .addAction(0, t("✅ It's OK"), action(false))
            .addAction(0, t("✅ Regular route"), action(true))
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(key.hashCode(), n) }
    }

    /** Remove this child's open route alerts (after "It's OK"). */
    fun clearRoute(ctx: Context, deviceId: String) {
        val nm = NotificationManagerCompat.from(ctx)
        ROUTE_KINDS.forEach { k -> nm.cancel("ai$deviceId$k".hashCode()) }
    }

    fun info(ctx: Context, key: String, title: String, text: String) {
        val pi = PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val n = NotificationCompat.Builder(ctx, SelfXApp.CH_INFO)
            .setSmallIcon(R.drawable.ic_shield).setContentTitle(title).setContentText(text)
            .setContentIntent(pi).setAutoCancel(true).build()
        runCatching { NotificationManagerCompat.from(ctx).notify(key.hashCode(), n) }
    }
}
