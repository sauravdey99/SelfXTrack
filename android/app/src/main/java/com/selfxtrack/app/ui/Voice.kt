package com.selfxtrack.app.ui

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.speech.RecognizerIntent
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import com.selfxtrack.app.i18n.t
import java.util.Locale

/** Reads answers aloud in the chosen language. Answers that came back in English use an Indian English voice. */
class Speaker(private val ctx: Context) {
    private var ready = false
    private val warned = mutableSetOf<String>()
    var speaking by mutableStateOf(false)
    private val tts = TextToSpeech(ctx.applicationContext) { ready = it == TextToSpeech.SUCCESS }.apply {
        setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(id: String?) {}
            override fun onDone(id: String?) { speaking = false }
            @Deprecated("Deprecated in Java") override fun onError(id: String?) { speaking = false }
        })
    }

    fun say(text: String, lang: AppLang) {
        if (!ready) return
        // Built-in answers for some languages are English – don't read English text with e.g. a Tamil voice.
        val native = text.any { it in '\u0600'..'\u06FF' || it in '\u0900'..'\u0DFF' }
        val loc = Locale.forLanguageTag(if (native) lang.tag else "en-IN")
        if (tts.isLanguageAvailable(loc) < TextToSpeech.LANG_AVAILABLE) {
            if (warned.add(lang.code)) Toast.makeText(ctx, t("{0} voice is not installed – Settings → Text-to-speech → Install voice data",
                lang.native), Toast.LENGTH_LONG).show()
            return
        }
        tts.language = loc
        // Emojis and symbols sound bad when read out.
        val clean = text.replace(Regex("[^\\p{L}\\p{M}\\p{N}\\p{P}\\s₹%]"), "").trim()
        speaking = true
        tts.speak(clean, TextToSpeech.QUEUE_FLUSH, null, "ans")
    }

    fun stop() { tts.stop(); speaking = false }
    fun shutdown() { tts.stop(); tts.shutdown() }
}

@Composable
fun rememberSpeaker(): Speaker {
    val ctx = LocalContext.current
    val speaker = remember { Speaker(ctx) }
    DisposableEffect(Unit) { onDispose { speaker.shutdown() } }
    return speaker
}

/** Returns a function that opens the system speech dialog in `lang` (plus English, for mixed speech). */
@Composable
fun rememberVoiceInput(lang: AppLang, onText: (String) -> Unit): () -> Unit {
    val ctx = LocalContext.current
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        if (r.resultCode == Activity.RESULT_OK) {
            r.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()
                ?.takeIf { it.isNotBlank() }?.let(onText)
        }
    }
    return {
        val i = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE, lang.tag)
            .putExtra("android.speech.extra.EXTRA_ADDITIONAL_LANGUAGES", arrayOf("en-IN"))
            .putExtra(RecognizerIntent.EXTRA_PROMPT, lang.native)
        try { launcher.launch(i) } catch (e: ActivityNotFoundException) {
            Toast.makeText(ctx, t("Voice input is not available on this phone"), Toast.LENGTH_SHORT).show()
        }
    }
}
