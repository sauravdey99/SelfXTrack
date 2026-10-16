package com.selfxtrack.app.live

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.RouteOkReq
import com.selfxtrack.app.data.userMessage
import com.selfxtrack.app.i18n.t
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/** Notification buttons "✅ It's OK" / "✅ Regular route" on a route alert – works while the app is closed. */
class RouteOkReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        val deviceId = intent.getStringExtra("device_id") ?: return
        val learn = intent.getBooleanExtra("learn", false)
        val done = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val r = runCatching { Api.api.routeOk(deviceId, RouteOkReq(learn = learn)) }
                Notifier.clearRoute(ctx, deviceId)
                Notifier.info(ctx, "routeok$deviceId", t("✅ Route alerts paused"),
                    r.fold({ (if (learn) t("Route learned.") + " " else "") +
                             t("Route alerts paused for this trip (until {0}).", it.until ?: "") },
                           { it.userMessage() }))
            } finally {
                done.finish()
            }
        }
    }
}
