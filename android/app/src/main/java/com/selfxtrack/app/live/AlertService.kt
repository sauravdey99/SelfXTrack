package com.selfxtrack.app.live

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.selfxtrack.app.R
import com.selfxtrack.app.SelfXApp
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.i18n.t
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

/**
 * Phase 1: keeps a WebSocket to the backend and raises SOS / alert notifications.
 * Phase 2: add Firebase Cloud Messaging so alerts arrive even when Android kills this service.
 */
class AlertService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var ws: WebSocket? = null
    private var running = true

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        val n = NotificationCompat.Builder(this, SelfXApp.CH_SERVICE)
            .setSmallIcon(R.drawable.ic_shield).setContentTitle(t("SelfXTrack is protecting your family"))
            .setOngoing(true).setPriority(NotificationCompat.PRIORITY_MIN).build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        else startForeground(1, n)
        scope.launch { connectLoop() }
        scope.launch { pollActiveSos() }
        scope.launch { while (running) { HelperLocation.upload(this@AlertService); delay(10 * 60_000) } }
    }

    private suspend fun connectLoop() {
        while (running) {
            val token = Api.session.token ?: return
            val url = Api.session.server.replaceFirst("http", "ws") + "/ws?token=$token"
            val closed = kotlinx.coroutines.CompletableDeferred<Unit>()
            ws = Api.client.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
                override fun onMessage(webSocket: WebSocket, text: String) = handle(JSONObject(text))
                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { closed.complete(Unit) }
                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    Log.w("AlertService", "ws failure: ${t.message}"); closed.complete(Unit)
                }
            })
            closed.await()
            delay(5000) // reconnect
        }
    }

    /** Safety net: if a WebSocket message was missed, still show active SOS. */
    private suspend fun pollActiveSos() {
        val shown = mutableSetOf<Int>()
        while (running) {
            runCatching { Api.api.activeSos() }.onSuccess { list ->
                list.filter { it.status == "active" && it.id !in shown }.forEach {
                    shown += it.id
                    Notifier.sos(this@AlertService, it.id, it.device_name ?: it.device_id ?: t("Tracker"))
                }
            }
            delay(30_000)
        }
    }

    private fun handle(e: JSONObject) {
        LiveEvents.emit(e)
        Notifier.handle(this, e.optString("type")) { k -> if (e.has(k) && !e.isNull(k)) e.get(k).toString() else null }
    }

    override fun onDestroy() {
        running = false; ws?.cancel(); scope.cancel(); super.onDestroy()
    }

    companion object {
        fun start(ctx: Context) = ctx.startForegroundService(Intent(ctx, AlertService::class.java))
        fun stop(ctx: Context) = ctx.stopService(Intent(ctx, AlertService::class.java))
    }
}
