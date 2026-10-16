package com.selfxtrack.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.TeacherContact
import com.selfxtrack.app.data.userMessage
import com.selfxtrack.app.i18n.t
import kotlinx.coroutines.launch

/** Teacher contacts for schools that are not on SelfXTrack. They get an SMS with a live link on "Emergency – School". */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TeacherContactsScreen(deviceId: String, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var list by remember { mutableStateOf<List<TeacherContact>>(emptyList()) }
    var name by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var msg by remember { mutableStateOf<String?>(null) }
    suspend fun load() { runCatching { Api.api.contacts(deviceId) }.onSuccess { list = it }.onFailure { msg = it.userMessage() } }
    LaunchedEffect(Unit) { load() }

    Scaffold(topBar = {
        TopAppBar(title = { Text(t("Teacher contacts")) },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) } })
    }) { pad ->
        Column(Modifier.padding(pad).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(t("If your school is not on SelfXTrack, add up to 5 teacher / staff numbers.") + " " +
                t("When you press “Emergency – School”, they get an SMS with a live location link. Please ask them first."))
            list.forEach { c ->
                val role = when (c.role) { "teacher" -> t("Teacher"); "staff" -> t("Staff"); "other" -> t("Other"); else -> c.role }
                ListItem(headlineContent = { Text(c.name) }, supportingContent = { Text("${c.phone} · $role") },
                    trailingContent = {
                        IconButton(onClick = { scope.launch { runCatching { Api.api.deleteContact(deviceId, c.id) }; load() } }) {
                            Icon(Icons.Default.Delete, t("Delete"))
                        }
                    })
            }
            OutlinedTextField(name, { name = it }, label = { Text(t("Name (e.g. Class teacher)")) }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(phone, { phone = it }, label = { Text(t("Mobile")) }, prefix = { Text("+91 ") }, modifier = Modifier.fillMaxWidth(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone))
            Button(enabled = name.isNotBlank() && phone.isNotBlank(), modifier = Modifier.fillMaxWidth(), onClick = {
                scope.launch {
                    runCatching { Api.api.addContact(deviceId, TeacherContact(name = name.trim(), phone = phone.trim())) }
                        .onSuccess { name = ""; phone = ""; msg = null; load() }.onFailure { msg = it.userMessage() }
                }
            }) { Text(t("Add contact")) }
            msg?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }
}
