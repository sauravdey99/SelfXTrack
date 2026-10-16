package com.selfxtrack.app.ui

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/** One calm blue palette for every screen: soft grey-blue background, white cards, navy accents.
 *  (Without the full set Material falls back to its default lilac for chips, FABs and containers.) */
val SelfXColors: ColorScheme = lightColorScheme(
    primary = Color(0xFF1F4E79), onPrimary = Color.White,
    primaryContainer = Color(0xFFD7E7F7), onPrimaryContainer = Color(0xFF0B2A45),
    secondary = Color(0xFF2E75B6), onSecondary = Color.White,
    secondaryContainer = Color(0xFFDDEBF9), onSecondaryContainer = Color(0xFF0D3558),
    tertiary = Color(0xFF00897B), onTertiary = Color.White,
    tertiaryContainer = Color(0xFFCDEDE9), onTertiaryContainer = Color(0xFF00352F),
    error = Color(0xFFC62828), errorContainer = Color(0xFFFFE3E3), onErrorContainer = Color(0xFF5F1111),
    background = Color(0xFFF4F7FB), onBackground = Color(0xFF1B1F24),
    surface = Color(0xFFF4F7FB), onSurface = Color(0xFF1B1F24),
    surfaceVariant = Color(0xFFE4EAF1), onSurfaceVariant = Color(0xFF4B5662),
    surfaceContainerLowest = Color.White, surfaceContainerLow = Color.White,
    surfaceContainer = Color(0xFFEEF2F7), surfaceContainerHigh = Color(0xFFE9EEF4), surfaceContainerHighest = Color(0xFFE3E9F0),
    outline = Color(0xFFB3BECA), outlineVariant = Color(0xFFDCE3EA),
)

private val SelfXShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp), small = RoundedCornerShape(12.dp), medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(20.dp), extraLarge = RoundedCornerShape(28.dp))

private val base = Typography()
private val SelfXType = base.copy(
    headlineSmall = base.headlineSmall.copy(fontWeight = FontWeight.Bold),
    titleLarge = base.titleLarge.copy(fontWeight = FontWeight.SemiBold),
    titleMedium = base.titleMedium.copy(fontWeight = FontWeight.SemiBold))

@Composable
fun SelfXTheme(content: @Composable () -> Unit) =
    MaterialTheme(colorScheme = SelfXColors, shapes = SelfXShapes, typography = SelfXType, content = content)
