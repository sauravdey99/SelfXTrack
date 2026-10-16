package com.selfxtrack.app.live

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import com.selfxtrack.app.data.Api
import com.selfxtrack.app.data.HelperLoc
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

/**
 * Emergency – Group: the phone shares an approximate position (every ~10 min) so the server can find
 * nearby helpers. Only used to match help requests; never shown to other users unless you accept a request.
 */
object HelperLocation {
    fun hasPermission(ctx: Context) =
        ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    @SuppressLint("MissingPermission")
    suspend fun upload(ctx: Context, precise: Boolean = false) {
        if (!hasPermission(ctx) || Api.session.token == null) return
        val client = LocationServices.getFusedLocationProviderClient(ctx)
        val loc = suspendCancellableCoroutine<android.location.Location?> { cont ->
            val cts = CancellationTokenSource()
            client.getCurrentLocation(if (precise) Priority.PRIORITY_HIGH_ACCURACY else Priority.PRIORITY_BALANCED_POWER_ACCURACY, cts.token)
                .addOnSuccessListener { cont.resume(it) }
                .addOnFailureListener { cont.resume(null) }
            cont.invokeOnCancellation { cts.cancel() }
        } ?: return
        runCatching { Api.api.helperLocation(HelperLoc(loc.latitude, loc.longitude)) }
    }
}
