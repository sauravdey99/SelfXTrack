package com.selfxtrack.app.live

import android.content.Context
import android.util.Log
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.selfxtrack.app.BuildConfig
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.FcmReq
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/** Firebase push: SOS / alerts arrive even when the app is closed. Disabled if firebase.properties is missing. */
class PushService : FirebaseMessagingService() {
    override fun onMessageReceived(msg: RemoteMessage) {
        val d = msg.data
        Notifier.handle(this, d["type"] ?: return) { d[it] }
    }

    override fun onNewToken(token: String) = upload(token)

    companion object {
        val enabled get() = BuildConfig.FB_APP_ID.isNotBlank()

        fun init(ctx: Context) {
            if (!enabled || FirebaseApp.getApps(ctx).isNotEmpty()) return
            FirebaseApp.initializeApp(ctx, FirebaseOptions.Builder()
                .setApiKey(BuildConfig.FB_API_KEY).setApplicationId(BuildConfig.FB_APP_ID)
                .setProjectId(BuildConfig.FB_PROJECT_ID).setGcmSenderId(BuildConfig.FB_SENDER_ID).build())
        }

        /** Call after login. */
        fun registerToken(ctx: Context) {
            if (!enabled) return
            init(ctx)
            FirebaseMessaging.getInstance().token.addOnSuccessListener { upload(it) }
                .addOnFailureListener { Log.w("PushService", "token failed: ${it.message}") }
        }

        private fun upload(token: String) {
            if (Api.session.token == null) return
            CoroutineScope(Dispatchers.IO).launch { runCatching { Api.api.setFcm(FcmReq(token)) } }
        }
    }
}
