package com.selfxtrack.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.selfxtrack.app.i18n.I18n
import com.selfxtrack.app.i18n.t

/** A language. `tag` is the BCP-47 locale used for speech recognition and text-to-speech. */
data class AppLang(val code: String, val native: String, val english: String, val tag: String)

/** Languages the AI assistant can listen and answer in. */
val LANGUAGES = listOf(
    AppLang("en", "English", "English", "en-IN"),
    AppLang("hi", "हिन्दी", "Hindi", "hi-IN"),
    AppLang("bn", "বাংলা", "Bengali", "bn-IN"),
    AppLang("ta", "தமிழ்", "Tamil", "ta-IN"),
    AppLang("te", "తెలుగు", "Telugu", "te-IN"),
    AppLang("mr", "मराठी", "Marathi", "mr-IN"),
    AppLang("gu", "ગુજરાતી", "Gujarati", "gu-IN"),
    AppLang("kn", "ಕನ್ನಡ", "Kannada", "kn-IN"),
    AppLang("ml", "മലയാളം", "Malayalam", "ml-IN"),
    AppLang("pa", "ਪੰਜਾਬੀ", "Punjabi", "pa-IN"),
    AppLang("or", "ଓଡ଼ିଆ", "Odia", "or-IN"),
    AppLang("ur", "اردو", "Urdu", "ur-IN"),
    AppLang("as", "অসমীয়া", "Assamese", "as-IN"),
)

/** Languages the app screens are translated into. */
val APP_LANGUAGES = LANGUAGES.filter { it.code in I18n.APP_LANGS }

fun appLang(code: String?): AppLang = LANGUAGES.firstOrNull { it.code == code } ?: LANGUAGES[0]

/**
 * Language settings: app (screen) language and AI language (voice + assistant answers).
 * firstRun = shown once on first start with a Continue button; otherwise it is the Settings screen.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LanguageSettingsScreen(appCode: String?, aiCode: String?, firstRun: Boolean,
                           onSave: (app: String, ai: String) -> Unit, onBack: () -> Unit = {}) {
    var app by remember { mutableStateOf(appLang(appCode ?: "en").takeIf { it in APP_LANGUAGES } ?: LANGUAGES[0]) }
    var ai by remember { mutableStateOf(appLang(aiCode ?: app.code)) }
    var aiTouched by remember { mutableStateOf(aiCode != null) }
    var picking by remember { mutableStateOf<String?>(null) }      // "app" | "ai"
    // Screens switch language right away so the user sees the choice.
    LaunchedEffect(app) { I18n.lang = app.code }

    Scaffold(topBar = {
        TopAppBar(title = { Text(if (firstRun) t("🌐 Choose language") else t("⚙️ Settings")) }, navigationIcon = {
            if (!firstRun) IconButton(onClick = { I18n.lang = appCode ?: "en"; onBack() }) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back"))
            }
        })
    }) { pad ->
        Column(Modifier.padding(pad).fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (firstRun) Text(t("You can change these any time in Settings."), color = Color.Gray)
            LangRow(t("App language"), t("Menus, buttons and screens"), app) { picking = "app" }
            LangRow(t("AI language"), t("Voice questions and assistant answers"), ai) { picking = "ai" }
            Spacer(Modifier.weight(1f))
            Button(onClick = { onSave(app.code, ai.code) }, Modifier.fillMaxWidth()) {
                Text(if (firstRun) t("Continue") else t("Save"))
            }
        }
    }

    picking?.let { which ->
        LangPicker(title = if (which == "app") t("App language") else t("AI language"),
            options = if (which == "app") APP_LANGUAGES else LANGUAGES,
            selected = if (which == "app") app else ai,
            onPick = { l ->
                if (which == "app") {
                    app = l
                    if (!aiTouched) ai = l                 // first choice: AI follows the app language
                } else { ai = l; aiTouched = true }
                picking = null
            }, onDismiss = { picking = null })
    }
}

@Composable
private fun LangRow(title: String, subtitle: String, value: AppLang, onClick: () -> Unit) {
    OutlinedCard(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleMedium)
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = Color.Gray)
            }
            Text(value.native, color = MaterialTheme.colorScheme.primary)
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null)
        }
    }
}

@Composable
private fun LangPicker(title: String, options: List<AppLang>, selected: AppLang, onPick: (AppLang) -> Unit,
                       onDismiss: () -> Unit) {
    AlertDialog(onDismissRequest = onDismiss, title = { Text(title) }, confirmButton = {},
        dismissButton = { TextButton(onClick = onDismiss) { Text(t("Cancel")) } },
        text = {
            LazyColumn(Modifier.heightIn(max = 420.dp)) {
                items(options) { l ->
                    Row(Modifier.fillMaxWidth().clickable { onPick(l) }.padding(vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(selected = l == selected, onClick = { onPick(l) })
                        Text(l.native, Modifier.weight(1f))
                        if (l.native != l.english) Text(l.english, color = Color.Gray)
                    }
                }
            }
        })
}
