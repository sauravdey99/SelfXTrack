package com.selfxtrack.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.selfxtrack.app.data.*
import com.selfxtrack.app.i18n.t
import kotlinx.coroutines.launch

/** Phase 4 – plans + Razorpay checkout (dev mode: test payment confirmed in the app). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlansScreen(onBack: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var plans by remember { mutableStateOf<List<PlanInfo>>(emptyList()) }
    var me by remember { mutableStateOf<BillingMe?>(null) }
    var yearly by remember { mutableStateOf(false) }
    var pending by remember { mutableStateOf<Pair<SubscribeRes, PlanInfo>?>(null) }
    var msg by remember { mutableStateOf<String?>(null) }

    suspend fun load() {
        runCatching { plans = Api.api.plans(); me = Api.api.billing() }.onFailure { msg = it.userMessage() }
    }
    LaunchedEffect(Unit) { load() }

    Scaffold(topBar = {
        TopAppBar(title = { Text(t("Plans")) },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) } })
    }) { pad ->
        Column(Modifier.padding(pad).padding(14.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            me?.let { m ->
                Text(t("Your plan: {0}", m.plan.replaceFirstChar { it.uppercase() }) +
                    (m.expires_at?.let { " · " + t("valid till {0}", it.take(10)) } ?: "") +
                    (if (m.status == "past_due") " · " + t("payment failed – {0}-day grace", m.grace_days) else "") +
                    (if (m.status == "cancelled") " · " + t("will not renew") else ""), fontWeight = FontWeight.Bold)
            }
            Text(t("SOS to family, Call 112 and live location always work – even if a payment fails."), color = Color.Gray)
            msg?.let { Text(it, color = MaterialTheme.colorScheme.secondary) }
            Row {
                FilterChip(!yearly, { yearly = false }, { Text(t("Monthly")) }, Modifier.padding(end = 6.dp))
                FilterChip(yearly, { yearly = true }, { Text(t("Yearly (save ~16%)")) })
            }
            plans.forEach { p ->
                val current = me?.plan == p.id
                Card(colors = CardDefaults.cardColors(containerColor = when (p.id) {
                    "guardian" -> Color(0xFFF3E5F5); "smart" -> Color(0xFFE3F2FD); else -> MaterialTheme.colorScheme.surfaceVariant })) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text("${p.name}  ₹${if (yearly) p.yearly else p.monthly}/" + (if (yearly) t("year") else t("month")),
                            fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                        p.features.forEach { Text("✓ $it") }
                        if (current) Text(t("✅ Current plan"), color = Color(0xFF2E7D32))
                        else Button(onClick = {
                            scope.launch {
                                runCatching { Api.api.subscribe(SubscribeReq(p.id, if (yearly) "yearly" else "monthly")) }
                                    .onSuccess { r ->
                                        if (r.checkout_url != null) {
                                            ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(r.checkout_url)))
                                            msg = t("Complete the payment (UPI AutoPay / card) in the browser, then come back.")
                                        } else pending = r to p
                                    }.onFailure { msg = it.userMessage() }
                            }
                        }) { Text(t("Choose {0}", p.name)) }
                    }
                }
            }
            if (me?.status == "active") TextButton(onClick = {
                scope.launch { runCatching { Api.api.cancelPlan() }.onSuccess { me = it; msg = t("Auto-renew stopped.") } }
            }) { Text(t("Stop auto-renew"), color = MaterialTheme.colorScheme.error) }
        }
    }

    pending?.let { (r, p) ->
        AlertDialog(onDismissRequest = { pending = null }, title = { Text(t("Test payment")) },
            text = { Text(t("Payments are in test mode (no Razorpay keys on the server). Confirm ₹{0} for {1}?", r.amount_inr, p.name)) },
            confirmButton = { TextButton(onClick = {
                scope.launch {
                    runCatching { Api.api.devConfirm(r.payment_id) }.onSuccess { me = it; msg = t("{0} plan active.", p.name) }
                        .onFailure { msg = it.userMessage() }
                    pending = null
                }
            }) { Text(t("Pay (test)")) } },
            dismissButton = { TextButton(onClick = { pending = null }) { Text(t("Cancel")) } })
    }
}
