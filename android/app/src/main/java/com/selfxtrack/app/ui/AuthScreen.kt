package com.selfxtrack.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.ForgotReq
import com.selfxtrack.app.data.LoginReq
import com.selfxtrack.app.data.ResetReq
import com.selfxtrack.app.data.RegisterReq
import com.selfxtrack.app.data.userMessage
import com.selfxtrack.app.i18n.t
import kotlinx.coroutines.launch

@Composable
fun AuthScreen(onLoggedIn: () -> Unit) {
    var register by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var server by remember { mutableStateOf(Api.session.server) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var consent by remember { mutableStateOf(false) }
    val ctx = androidx.compose.ui.platform.LocalContext.current
    var forgot by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally) {
        Text("SelfXTrack", fontSize = 32.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
        Text(t("Family safety tracker"), color = MaterialTheme.colorScheme.secondary)
        Spacer(Modifier.height(24.dp))
        if (register) OutlinedTextField(name, { name = it }, label = { Text(t("Your name")) }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(email, { email = it }, label = { Text(t("Email")) }, modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
        OutlinedTextField(password, { password = it }, label = { Text(if (register) t("New password (8+)") else t("Password")) }, modifier = Modifier.fillMaxWidth(),
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
        OutlinedTextField(server, { server = it }, label = { Text(t("Server address")) }, modifier = Modifier.fillMaxWidth(),
            singleLine = true)
        if (register) Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Checkbox(consent, { consent = it })
            Text(t("I agree to the Terms and Privacy Policy and give consent, as parent / guardian, for my child's location to be processed for safety."),
                style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
        }
        if (register) Row {
            TextButton(onClick = { ctx.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW,
                android.net.Uri.parse(server.trimEnd('/') + "/privacy"))) }) { Text(t("Privacy Policy")) }
            TextButton(onClick = { ctx.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW,
                android.net.Uri.parse(server.trimEnd('/') + "/terms"))) }) { Text(t("Terms")) }
        }
        error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 8.dp)) }
        Spacer(Modifier.height(16.dp))
        Button(enabled = !busy && (!register || (consent && password.length >= 8)), modifier = Modifier.fillMaxWidth(), onClick = {
            busy = true; error = null
            scope.launch {
                runCatching {
                    Api.session.setServer(server)
                    if (register) Api.api.register(RegisterReq(email.trim(), name.trim(), password, consent = consent))
                    else Api.api.login(LoginReq(email.trim(), password))
                }.onSuccess { Api.session.save(it.access_token, it.name); onLoggedIn() }
                    .onFailure { error = it.userMessage() }
                busy = false
            }
        }) { Text(if (register) t("Create account") else t("Log in")) }
        TextButton(onClick = { register = !register }) {
            Text(if (register) t("Have an account? Log in") else t("New here? Create an account"))
        }
        if (!register) TextButton(onClick = { forgot = true }) { Text(t("Forgot password?")) }
    }

    if (forgot) ForgotPasswordDialog(email, server, onDone = { m -> forgot = false; m?.let { error = it } })
}

@Composable
private fun ForgotPasswordDialog(initialEmail: String, server: String, onDone: (String?) -> Unit) {
    val scope = rememberCoroutineScope()
    var email by remember { mutableStateOf(initialEmail) }
    var code by remember { mutableStateOf("") }
    var pass by remember { mutableStateOf("") }
    var sent by remember { mutableStateOf(false) }
    var info by remember { mutableStateOf<String?>(null) }
    AlertDialog(onDismissRequest = { onDone(null) }, title = { Text(t("Reset password")) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(email, { email = it }, label = { Text(t("Account email")) }, enabled = !sent, singleLine = true)
                if (sent) {
                    OutlinedTextField(code, { code = it }, label = { Text(t("OTP sent to your mobile")) }, singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword))
                    OutlinedTextField(pass, { pass = it }, label = { Text(t("New password (8+)")) }, singleLine = true,
                        visualTransformation = PasswordVisualTransformation())
                }
                info?.let { Text(it, color = MaterialTheme.colorScheme.secondary) }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                scope.launch {
                    Api.session.setServer(server)
                    if (!sent) runCatching { Api.api.forgot(ForgotReq(email.trim())) }.onSuccess {
                        sent = true
                        info = it.message + (it.phone_hint?.let { h -> " ($h)" } ?: "") + (it.dev_code?.let { c -> "\n" + t("Test mode OTP: {0}", c) } ?: "")
                    }.onFailure { info = it.userMessage() }
                    else runCatching { Api.api.reset(ResetReq(email.trim(), code.trim(), pass)) }
                        .onSuccess { onDone(t("Password changed. Log in with the new password.")) }.onFailure { info = it.userMessage() }
                }
            }) { Text(if (sent) t("Change password") else t("Send OTP")) }
        }, dismissButton = { TextButton(onClick = { onDone(null) }) { Text(t("Cancel")) } })
}
