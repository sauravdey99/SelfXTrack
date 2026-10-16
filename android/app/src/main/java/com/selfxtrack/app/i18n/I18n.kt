package com.selfxtrack.app.i18n

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/**
 * App (screen) language. Texts are written in English in the code and wrapped in `t("…")`; the English text is
 * the key into the per-language tables below. Missing entries fall back to English, so a half-translated
 * language still works. Placeholders: `t("Ask about {0}", name)`.
 *
 * This is separate from the AI language (voice + assistant answers), which is stored in Session.aiLang.
 */
object I18n {
    /** Changing this recomposes every screen that called t(). */
    var lang by mutableStateOf("en")

    private val parts = listOf(trAsk, trChild, trSchool, trMain, trSos, trSettings)
    private val tables: Map<String, Map<String, String>> by lazy {
        mapOf("hi" to parts.fold(emptyMap()) { a, p -> a + p.hi }, "bn" to parts.fold(emptyMap()) { a, p -> a + p.bn },
            "ta" to langTa, "te" to langTe, "mr" to langMr, "gu" to langGu, "kn" to langKn, "ml" to langMl,
            "pa" to langPa, "or" to langOr, "ur" to langUr, "as" to langAs)
            // places / transport screens: TrPlacesA.kt (hi bn ta te mr gu) + TrPlacesB.kt (kn ml pa or ur as)
            .mapValues { (lang, m) -> m + (trPlacesA[lang] ?: emptyMap()) + (trPlacesB[lang] ?: emptyMap()) +
                (trRouteOk[lang] ?: emptyMap()) + (trMenu[lang] ?: emptyMap()) + (trBrief[lang] ?: emptyMap()) }
    }

    /** Languages with screen translations (one Lang<Code>.kt file each, hi/bn live in the Tr*.kt files). */
    val APP_LANGS = listOf("en", "hi", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa", "or", "ur", "as")

    /** Urdu is written right-to-left. */
    val rtl: Boolean get() = lang == "ur"

    fun lookup(en: String): String = if (lang == "en") en else tables[lang]?.get(en) ?: en
}

/** Translations for one group of screens. Keys are the exact English strings passed to t(). */
class Tr(val hi: Map<String, String>, val bn: Map<String, String>)

fun t(en: String, vararg args: Any?): String =
    args.foldIndexed(I18n.lookup(en)) { i, s, a -> s.replace("{$i}", a.toString()) }
