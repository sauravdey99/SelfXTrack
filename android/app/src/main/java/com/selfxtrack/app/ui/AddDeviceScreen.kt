package com.selfxtrack.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.ClaimReq
import com.selfxtrack.app.data.userMessage
import com.selfxtrack.app.i18n.t
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddDeviceScreen(onBack: () -> Unit, onDone: (String) -> Unit) {
    var deviceId by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var kind by remember { mutableStateOf("child") }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val kinds = listOf("child" to t("Child"), "elderly" to t("Elderly"), "pet" to t("Pet"), "bike" to t("Bike"), "bag" to t("Bag"))

    Scaffold(topBar = {
        TopAppBar(title = { Text(t("Add tracker")) }, navigationIcon = {
            IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, t("Back")) }
        })
    }) { pad ->
        Column(Modifier.padding(pad).padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(t("Enter the Device ID and Claim Code printed on the card in the box."))
            OutlinedTextField(deviceId, { deviceId = it }, label = { Text(t("Device ID (e.g. SX-0001)")) }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(code, { code = it.uppercase() }, label = { Text(t("Claim code")) }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(name, { name = it }, label = { Text(t("Who wears it? (name)")) }, modifier = Modifier.fillMaxWidth())
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                kinds.forEach { (k, label) -> FilterChip(selected = kind == k, onClick = { kind = k }, label = { Text(label) }) }
            }
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            Button(modifier = Modifier.fillMaxWidth(), enabled = deviceId.isNotBlank() && code.isNotBlank() && name.isNotBlank(),
                onClick = {
                    scope.launch {
                        runCatching { Api.api.claim(ClaimReq(deviceId.trim(), code.trim(), name.trim(), kind)) }
                            .onSuccess { onDone(it.device_id) }.onFailure { error = it.userMessage() }
                    }
                }) { Text(t("Add")) }
        }
    }
}
