package com.selfxtrack.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.OtpReq
import com.selfxtrack.app.data.OtpVerifyReq
import com.selfxtrack.app.data.userMessage
import com.selfxtrack.app.i18n.t
import kotlinx.coroutines.launch

/** Every account verifies its mobile by OTP (safety of the emergency network). */
@Composable
fun VerifyPhoneScreen(onVerified: () -> Unit) {
    val scope = rememberCoroutineScope()
    var phone by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var sent by remember { mutableStateOf(false) }
    var info by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Spacer(Modifier.height(40.dp))
        Text(t("Verify your mobile"), fontSize = 26.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
        Text(t("For everyone's safety, every SelfXTrack account verifies a mobile number. It is used for emergency alerts and password recovery."))
        OutlinedTextField(phone, { phone = it }, label = { Text(t("Mobile number")) }, prefix = { Text("+91 ") },
            enabled = !sent, singleLine = true, modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone))
        if (sent) OutlinedTextField(code, { if (it.length <= 6) code = it }, label = { Text(t("6-digit OTP")) }, singleLine = true,
            modifier = Modifier.fillMaxWidth(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword))
        info?.let { Text(it, color = MaterialTheme.colorScheme.secondary) }
        Button(enabled = !busy, modifier = Modifier.fillMaxWidth(), onClick = {
            busy = true; info = null
            scope.launch {
                if (!sent) runCatching { Api.api.requestOtp(OtpReq(phone.trim())) }
                    .onSuccess { phone = it.phone; sent = true; it.dev_code?.let { c -> info = t("Test mode OTP: {0}", c) } }
                    .onFailure { info = it.userMessage() }
                else runCatching { Api.api.verifyOtp(OtpVerifyReq(phone, code.trim())) }
                    .onSuccess { onVerified() }.onFailure { info = it.userMessage() }
                busy = false
            }
        }) { Text(if (sent) t("Verify") else t("Send OTP")) }
        if (sent) TextButton(onClick = { sent = false; code = "" }) { Text(t("Change number / resend")) }
    }
}
