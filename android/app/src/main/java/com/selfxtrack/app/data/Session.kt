package com.selfxtrack.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.selfxtrack.app.BuildConfig
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.runBlocking

private val Context.store by preferencesDataStore("selfx")
private val KEY_TOKEN = stringPreferencesKey("token")
private val KEY_NAME = stringPreferencesKey("name")
private val KEY_SERVER = stringPreferencesKey("server")
private val KEY_LANG = stringPreferencesKey("lang")          // AI language (voice + assistant)
private val KEY_APP_LANG = stringPreferencesKey("app_lang")  // screen language

/** Stores login token, server address and the chosen language. */
class Session(private val ctx: Context) {
    val tokenFlow = ctx.store.data.map { it[KEY_TOKEN] }

    @Volatile var token: String? = runBlocking { ctx.store.data.first()[KEY_TOKEN] }
        private set
    @Volatile var server: String = runBlocking { ctx.store.data.first()[KEY_SERVER] } ?: BuildConfig.DEFAULT_SERVER
        private set
    var name: String? = runBlocking { ctx.store.data.first()[KEY_NAME] }
        private set
    /** AI language for voice + assistant answers (en, hi, bn, ta, …). */
    var aiLang: String? = runBlocking { ctx.store.data.first()[KEY_LANG] }
        private set
    /** Screen language; null until picked on the first-run screen. */
    var appLang: String? = runBlocking { ctx.store.data.first()[KEY_APP_LANG] }
        private set

    suspend fun setLanguages(app: String, ai: String) {
        appLang = app; aiLang = ai
        ctx.store.edit { it[KEY_APP_LANG] = app; it[KEY_LANG] = ai }
    }

    suspend fun save(token: String, name: String) {
        this.token = token; this.name = name
        ctx.store.edit { it[KEY_TOKEN] = token; it[KEY_NAME] = name }
    }

    suspend fun setServer(url: String) {
        server = url.trimEnd('/')
        ctx.store.edit { it[KEY_SERVER] = server }
        Api.reset()
    }

    suspend fun logout() {
        token = null; name = null
        ctx.store.edit { it.remove(KEY_TOKEN); it.remove(KEY_NAME) }
    }
}
