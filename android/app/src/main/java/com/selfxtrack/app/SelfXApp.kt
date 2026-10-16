package com.selfxtrack.app

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.media.AudioAttributes
import android.media.RingtoneManager
import com.selfxtrack.app.data.Session

class SelfXApp : Application() {
    lateinit var session: Session
        private set

    override fun onCreate() {
        super.onCreate()
        session = Session(this)
        com.selfxtrack.app.data.Api.session = session      // notification buttons work while the app is closed
        com.selfxtrack.app.i18n.I18n.lang = session.appLang ?: "en"
        val nm = getSystemService(NotificationManager::class.java)
        val sos = NotificationChannel(CH_SOS, "SOS alerts", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Emergency SOS from a tracker"
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 800, 300, 800, 300, 800)
            setSound(
                RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM),
                AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).build()
            )
            setBypassDnd(true)
        }
        val info = NotificationChannel(CH_INFO, "Tracker alerts", NotificationManager.IMPORTANCE_DEFAULT)
        val svc = NotificationChannel(CH_SERVICE, "Live connection", NotificationManager.IMPORTANCE_MIN)
        nm.createNotificationChannels(listOf(sos, info, svc))
    }

    companion object {
        const val CH_SOS = "sos"
        const val CH_INFO = "info"
        const val CH_SERVICE = "service"
    }
}
