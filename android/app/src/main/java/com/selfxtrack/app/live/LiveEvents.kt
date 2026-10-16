package com.selfxtrack.app.live

import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import org.json.JSONObject

/** Live events pushed by the backend over WebSocket (location, sos, sos_update, low_battery). */
object LiveEvents {
    private val _events = MutableSharedFlow<JSONObject>(extraBufferCapacity = 64, onBufferOverflow = BufferOverflow.DROP_OLDEST)
    val events = _events.asSharedFlow()
    fun emit(e: JSONObject) { _events.tryEmit(e) }
}
