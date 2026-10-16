package com.selfxtrack.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.selfxtrack.app.data.*
import com.selfxtrack.app.i18n.t
import com.selfxtrack.app.live.LiveEvents
import kotlinx.coroutines.launch

/** School safety circle: register a school (admin), join as staff (OTP + admin approval), staff list, SOS board. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SchoolScreen(onBack: () -> Unit, onOpenSos: (Int) -> Unit) {
    val scope = rememberCoroutineScope()
    var schools by remember { mutableStateOf<List<School>>(emptyList()) }
    var staff by remember { mutableStateOf<Map<Int, List<Staff>>>(emptyMap()) }
    var showCreate by remember { mutableStateOf(false) }
    var showJoin by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf<String?>(null) }

    suspend fun load() {
        runCatching { Api.api.schools() }.onSuccess { list ->
            schools = list
            staff = list.filter { it.role == "admin" }.associate { s -> s.id to (runCatching { Api.api.staff(s.id) }.getOrDefault(emptyList())) }
        }.onFailure { msg = it.userMessage() }
    }
    LaunchedEffect(Unit) { load() }

    Scaffold(topBar = {
        TopAppBar(title = { Text(t("School safety circle")) },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) } })
    }) { pad ->
        LazyColumn(Modifier.padding(pad).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                Text(t("Teachers, security and bus staff receive a student's SOS only if the parent links the tracker to the school.") + " " +
                    t("Staff see location only while an SOS is active."))
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { showJoin = true }) { Text(t("Join as staff")) }
                    OutlinedButton(onClick = { showCreate = true }) { Text(t("Register a school")) }
                }
            }
            msg?.let { item { Text(it, color = MaterialTheme.colorScheme.secondary) } }
            items(schools, key = { it.id }) { s ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(s.name, fontWeight = FontWeight.Bold)
                        Text(t("Your role: {0}", t(s.role)) + if (s.status == "pending") "  ·  " + t("⏳ waiting for admin approval") else "")
                        if (s.staff_code != null) SelectionContainer {
                            Column {
                                Text(t("Staff code: {0}  (give to teachers / security / bus staff)", s.staff_code))
                                Text(t("Parent code: {0}  (give to parents)", s.parent_code))
                            }
                        }
                        if (s.status == "approved")
                            TextButton(onClick = { onOpenSos(s.id) }) { Icon(Icons.Default.Warning, null); Text(" " + t("Student SOS board")) }

                        staff[s.id]?.let { list ->
                            HorizontalDivider(Modifier.padding(vertical = 6.dp))
                            Text(t("Staff ({0})", list.size), fontWeight = FontWeight.Bold)
                            list.forEach { st ->
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Column(Modifier.weight(1f)) {
                                        Text("${st.name} · ${t(st.role)}")
                                        Text("${st.phone ?: st.email}" + if (st.status == "pending") "  ·  " + t("pending") else "  ·  " + t("✅ approved"),
                                            color = if (st.status == "pending") Color(0xFFB26A00) else Color(0xFF2E7D32))
                                    }
                                    if (st.status == "pending") TextButton(onClick = {
                                        scope.launch { runCatching { Api.api.approveStaff(s.id, st.user_id) }.onFailure { msg = it.userMessage() }; load() }
                                    }) { Text(t("Approve")) }
                                    if (st.role != "admin") IconButton(onClick = {
                                        scope.launch { runCatching { Api.api.removeStaff(s.id, st.user_id) }.onFailure { msg = it.userMessage() }; load() }
                                    }) { Icon(Icons.Default.PersonRemove, t("Remove")) }
                                }
                            }
                            if (list.none { it.role != "admin" }) Text(t("You are the school admin (you registered this school). No teachers yet – share the staff code with them."), color = Color.Gray)
                        }
                    }
                }
            }
        }
    }

    if (showCreate) {
        var name by remember { mutableStateOf("") }
        AlertDialog(onDismissRequest = { showCreate = false }, title = { Text(t("Register a school")) },
            text = { OutlinedTextField(name, { name = it }, label = { Text(t("School name")) }) },
            confirmButton = {
                TextButton(enabled = name.isNotBlank(), onClick = {
                    scope.launch {
                        runCatching { Api.api.createSchool(SchoolReq(name.trim())) }
                            .onSuccess { msg = t("School registered. Share the codes below.") ; load() }.onFailure { msg = it.userMessage() }
                        showCreate = false
                    }
                }) { Text(t("Register")) }
            }, dismissButton = { TextButton(onClick = { showCreate = false }) { Text(t("Cancel")) } })
    }

    if (showJoin) JoinStaffDialog(onDone = { m -> showJoin = false; m?.let { msg = it }; scope.launch { load() } })
}

/** Step 1: verify mobile with OTP. Step 2: enter staff code + role → request sent to school admin. */
@Composable
private fun JoinStaffDialog(onDone: (String?) -> Unit) {
    val scope = rememberCoroutineScope()
    var step by remember { mutableIntStateOf(0) }   // 0 = loading, 1 = phone, 2 = otp, 3 = code
    var phone by remember { mutableStateOf("") }
    var otp by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var role by remember { mutableStateOf("teacher") }
    var info by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        runCatching { Api.api.me() }.onSuccess { step = if (it.phone_verified) 3 else 1; phone = it.phone ?: "" }
            .onFailure { step = 1 }
    }

    AlertDialog(onDismissRequest = { onDone(null) },
        title = { Text(when (step) { 1 -> t("Verify your mobile"); 2 -> t("Enter OTP"); 3 -> t("Join school as staff"); else -> t("Please wait") }) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                when (step) {
                    1 -> {
                        Text(t("School staff must verify their mobile number."))
                        OutlinedTextField(phone, { phone = it }, label = { Text(t("Mobile number")) }, prefix = { Text("+91 ") },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone), singleLine = true)
                    }
                    2 -> {
                        Text(t("We sent a 6-digit code to {0}.", phone))
                        OutlinedTextField(otp, { if (it.length <= 6) otp = it }, label = { Text(t("OTP")) },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword), singleLine = true)
                        TextButton(onClick = { step = 1; otp = "" }) { Text(t("Change number / resend")) }
                    }
                    3 -> {
                        Text(t("✅ Mobile verified: {0}", phone))
                        OutlinedTextField(code, { code = it.uppercase() }, label = { Text(t("Staff code from the school")) }, singleLine = true)
                        Row {
                            listOf("teacher", "security", "bus").forEach { r ->
                                FilterChip(selected = role == r, onClick = { role = r }, label = { Text(t(r)) }, modifier = Modifier.padding(end = 4.dp))
                            }
                        }
                        Text(t("The school admin must approve you before you receive student SOS alerts."), color = Color.Gray)
                    }
                    else -> CircularProgressIndicator()
                }
                info?.let { Text(it, color = MaterialTheme.colorScheme.secondary) }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy && step != 0, onClick = {
                busy = true; info = null
                scope.launch {
                    when (step) {
                        1 -> runCatching { Api.api.requestOtp(OtpReq(phone.trim())) }.onSuccess {
                            phone = it.phone; step = 2
                            it.dev_code?.let { c -> info = t("Test mode OTP: {0}", c) }   // shown only when server runs in dev mode
                        }.onFailure { info = it.userMessage() }
                        2 -> runCatching { Api.api.verifyOtp(OtpVerifyReq(phone, otp.trim())) }
                            .onSuccess { step = 3; info = null }.onFailure { info = it.userMessage() }
                        3 -> runCatching { Api.api.joinSchool(JoinSchoolReq(code.trim(), role)) }
                            .onSuccess { onDone(t("Request sent to {0}. Waiting for the school admin's approval.", it.name)) }
                            .onFailure { info = it.userMessage() }
                    }
                    busy = false
                }
            }) { Text(when (step) { 1 -> t("Send OTP"); 2 -> t("Verify"); else -> t("Send request") }) }
        },
        dismissButton = { TextButton(onClick = { onDone(null) }) { Text(t("Cancel")) } })
}

/** For teachers / security: active student SOS with emergency info pack. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SchoolSosScreen(schoolId: Int, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var list by remember { mutableStateOf<List<SchoolSos>>(emptyList()) }
    var msg by remember { mutableStateOf<String?>(null) }

    suspend fun load() { runCatching { Api.api.schoolSos(schoolId) }.onSuccess { list = it; msg = null }.onFailure { msg = it.userMessage() } }
    LaunchedEffect(Unit) { load() }
    LaunchedEffect(Unit) { LiveEvents.events.collect { load() } }

    Scaffold(topBar = {
        TopAppBar(title = { Text(t("Student SOS")) },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) } })
    }) { pad ->
        LazyColumn(Modifier.padding(pad).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (list.isEmpty()) item { Text(msg ?: t("No active SOS. ✅")) }
            if (list.isNotEmpty()) msg?.let { item { Text(it, color = MaterialTheme.colorScheme.secondary) } }
            items(list, key = { it.sos_id }) { s ->
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFFFEBEE))) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text("🚨 ${s.name}" + (s.class_name?.let { " · " + t("Class {0}", it) } ?: ""), fontWeight = FontWeight.Bold, color = Color(0xFFC62828))
                        Text(t("SOS {0} · status {1}", ago(s.started_at), t(s.status)))
                        Text(t("Last update {0} · battery {1}%", ago(s.last_seen), s.battery ?: "–") +
                            (s.speed_kmh?.let { " · " + t("{0} km/h", it.toInt()) } ?: "") + (s.heading_deg?.let { " · " + t("heading {0}°", it.toInt()) } ?: ""))
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Button(onClick = { ctx.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:112"))) },
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFC62828))) { Text(t("Call 112")) }
                            OutlinedButton(enabled = s.lat != null, onClick = {
                                ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("google.navigation:q=${s.lat},${s.lon}")))
                            }) { Text(t("Navigate")) }
                            if (s.status == "active") OutlinedButton(onClick = {
                                scope.launch { runCatching { Api.api.acknowledge(s.sos_id) }; load() }
                            }) { Text(t("I'm on it")) }
                        }
                        if (!s.school_alerted) Text(t("Parents have not escalated yet – shown here because the child pressed SOS."),
                            color = Color.Gray)
                        Text(t("Do not confront anyone. Observe, inform the family and police."), color = Color.Gray)
                    }
                }
            }
        }
    }
}
