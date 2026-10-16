package com.selfxtrack.app.data

import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query
import java.util.concurrent.TimeUnit

// ---- Models (match backend/app/schemas.py) ----
data class RegisterReq(val email: String, val name: String, val password: String, val phone: String? = null,
                       val consent: Boolean = true)
data class DeleteReq(val password: String)
data class LoginReq(val email: String, val password: String)
data class TokenRes(val access_token: String, val user_id: Int, val name: String)
data class ClaimReq(val device_id: String, val claim_code: String, val name: String, val kind: String = "child")
data class ShareReq(val email: String)
data class SetupSchool(val id: Int, val name: String, val class_name: String?)
data class FamilyMember(val name: String?, val email: String, val phone: String? = null, val role: String)
data class FamilyInvite(val id: Int, val name: String, val phone: String, val ready: Boolean, val relation: String = "family")
data class MySchool(val name: String, val children: List<String>, val contacts: List<TeacherContact> = emptyList())
data class InviteReq(val name: String, val phone: String, val relation: String = "family")
data class RoleReq(val relation: String)
data class BusItem(val id: Int, val name: String, val beacon_id: String, val on_now: Boolean = false)
data class BusReq(val name: String, val beacon_id: String, val all_children: Boolean = false)
data class Care(val kind: String = "child", val fall_detection: Boolean = true, val inactivity_hours: Int = 3,
                val active_from: String = "08:00", val active_to: String = "21:00", val last_active_at: String? = null)
data class CareReq(val fall_detection: Boolean? = null, val inactivity_hours: Int? = null,
                   val active_from: String? = null, val active_to: String? = null)
data class ChildSetup(val device_id: String, val name: String?, val kind: String, val schools: List<SetupSchool> = emptyList(),
                      val manual_school: String?, val manual_class: String?, val contacts: Int = 0,
                      val family: List<FamilyMember> = emptyList(),
                      val invites: List<FamilyInvite> = emptyList(), val public_holidays: Boolean = true)
data class SetupReq(val name: String? = null, val kind: String? = null, val manual_school: String? = null, val manual_class: String? = null,
                    val public_holidays: Boolean? = null)
data class Device(
    val device_id: String, val name: String?, val kind: String, val last_seen: String?,
    val last_lat: Double?, val last_lon: Double?, val last_accuracy: Double?,
    val battery: Int?, val charging: Boolean, val online: Boolean, val active_sos: Int?
)
data class Point(val ts: String, val lat: Double, val lon: Double, val accuracy: Double?,
                 val speed: Double?, val heading: Double?, val battery: Int?, val source: String)
data class Sos(val id: Int, val device_id: String?, val device_name: String?, val started_at: String,
               val lat: Double?, val lon: Double?, val status: String, val responder: String? = null,
               val acknowledged_at: String? = null, val source: String? = null)

// Phase 2
data class FcmReq(val token: String)
data class LangReq(val lang: String)
data class Geofence(val id: Int = 0, val name: String, val lat: Double, val lon: Double, val radius_m: Int = 150,
                    val notify_enter: Boolean = true, val notify_exit: Boolean = true, val inside: Boolean? = null)
data class ShareLinkReq(val minutes: Int = 60, val for_sos: Boolean = false)
data class ShareLink(val token: String, val url: String, val expires_at: String, val active: Boolean)
data class SchoolReq(val name: String)
data class School(val id: Int, val name: String, val role: String, val status: String = "approved",
                  val staff_code: String?, val parent_code: String?)
data class Staff(val user_id: Int, val name: String, val phone: String?, val email: String, val role: String, val status: String)
data class OtpReq(val phone: String)
data class OtpVerifyReq(val phone: String, val code: String)
data class OtpRes(val ok: Boolean, val phone: String, val dev_code: String?)
data class Me(val id: Int, val name: String, val email: String, val phone: String?, val phone_verified: Boolean,
              val plan: String = "basic", val helper_available: Boolean = true)

// Phase 3
data class EmergencyReq(val target: String, val place_id: Int? = null)
data class EmergencyRes(val sos_id: Int, val target: String, val notified: Int? = null, val radius_m: Int? = null,
                        val staff: Int? = null, val contacts: Int? = null, val warning: String? = null, val help_id: Int? = null,
                        val people: Int? = null, val place: String? = null)
data class GroupInfo(val help_id: Int, val radius_m: Int, val notified: Int, val accepted: Int, val closed: Boolean)
data class HelperInfo(val user_id: Int, val name: String, val phone: String?, val distance_m: Int?, val lat: Double?, val lon: Double?)
data class AccessLog(val name: String, val kind: String, val ts: String)
data class SosStatus(val sos_id: Int, val status: String, val source: String, val plan: String, val school_notified_at: String?,
                     val group: GroupInfo?, val helpers: List<HelperInfo>, val access_log: List<AccessLog>,
                     val alerted_to: List<String>? = null)   // null from older servers
data class TeacherContact(val id: Int = 0, val name: String, val phone: String, val role: String = "teacher",
                          val place_id: Int? = null)

// ---- Places (any number) with time slots + people, and Transport
data class Slot(val days: List<Int>, val start: String, val end: String)       // days 0=Mon … 6=Sun
data class Person(val id: Int = 0, val name: String, val phone: String, val role: String = "other")
data class ChildPlace(val id: Int, val name: String, val kind: String, val lat: Double, val lon: Double, val radius_m: Int,
                 val note: String? = null, val schedule: List<Slot> = emptyList(), val alert_late: Boolean = true,
                 val notify_enter: Boolean = true, val notify_exit: Boolean = true, val inside: Boolean? = null,
                 val people: List<Person> = emptyList())
data class PlaceReq(val name: String, val kind: String, val lat: Double, val lon: Double, val radius_m: Int,
                    val note: String?, val schedule: List<Slot>, val alert_late: Boolean,
                    val notify_enter: Boolean, val notify_exit: Boolean)
data class PersonReq(val name: String, val phone: String, val role: String)
data class Transport(val id: Int, val name: String, val kind: String, val beacon_id: String? = null,
                     val driver_name: String? = null, val driver_phone: String? = null,
                     val place_ids: List<Int> = emptyList(), val on_now: Boolean = false)
data class TransportReq(val name: String, val kind: String, val beacon_id: String?, val driver_name: String?,
                        val driver_phone: String?, val place_ids: List<Int>, val all_children: Boolean = false)
data class NowPlace(val id: Int, val name: String, val kind: String)
data class TodaySlot(val place: String, val kind: String, val start: String, val end: String)
data class NowInfo(val place: NowPlace? = null, val from: String? = null, val until: String? = null,
                   val inside: Boolean? = null, val people: List<Person> = emptyList(),
                   val today: List<TodaySlot> = emptyList(),
                   val route_paused_until: String? = null, val route_paused_trip: Boolean? = null,
                   val trip: CurrentTrip? = null)
/** The journey the child is on right now (null when not travelling). */
data class CurrentTrip(val started_at: String? = null, val started_from: String? = null, val heading_to: String? = null,
                       val eta_time: String? = null, val eta_minutes: Int? = null, val km_so_far: Double? = null)
data class RouteOkReq(val learn: Boolean = false, val minutes: Int? = null)  // minutes null = this trip only
data class RouteOkRes(val until: String? = null, val trip: Boolean? = null, val learned_points: Int? = null)
data class HelperLoc(val lat: Double, val lon: Double)
data class Availability(val available: Boolean)
data class FamilyContact(val name: String, val phone: String?)
data class HelpDetail(val help_id: Int, val closed: Boolean, val status: String? = null, val distance_m: Int? = null,
                      val message: String? = null, val name: String? = null, val lat: Double? = null, val lon: Double? = null,
                      val speed_kmh: Double? = null, val heading_deg: Double? = null, val battery: Int? = null,
                      val last_seen: String? = null, val family: List<FamilyContact>? = null, val safety: String? = null,
                      val sos_id: Int? = null)
data class BoardChild(val device_id: String, val name: String, val school: String?, val class_name: String?,
                      val my_role: String, val sos: SchoolSos?, val parents: List<BoardParent> = emptyList(),
                      val place_kind: String? = null, val kind: String? = null)   // null from older servers
data class BoardParent(val name: String?, val phone: String?, val role: String, val raised: Boolean = false)
data class LatLon(val lat: Double, val lon: Double)
data class StaffTrack(val name: String, val lat: Double?, val lon: Double?, val accuracy_m: Double?, val speed_kmh: Double?,
                      val battery: Int?, val last_seen: String?, val started_at: String?, val status: String,
                      val trail: List<LatLon> = emptyList())
data class StaffBoard(val verified: Boolean, val children: List<BoardChild>)
data class Place(val name: String, val lat: Double, val lon: Double, val visits: Int, val days: Int,
                 val usual_arrival: String, val avg_stay_min: Int)
data class Eta(val to: String, val minutes: Int?, val distance_m: Int, val text: String)
data class Trip(val from: String, val to: String, val median_min: Int, val usual_depart: String,
                val usual_arrive: String, val count: Int)
data class AiAlertItem(val time: String, val kind: String, val text: String)
data class Insights(val locked: Boolean, val plan: String, val learning_days: Int = 0, val ready: Boolean = false,
                    val min_days: Int = 5, val places: List<Place> = emptyList(), val eta: Eta? = null,
                    val alerts: List<AiAlertItem> = emptyList(), val assistant_ai: Boolean = false,
                    val trips: List<Trip> = emptyList(), val holiday_today: Boolean = false,
                    val battery: BatteryForecast? = null,
                    val holiday_question: Boolean = false)
data class HolidayItem(val day: String, val note: String?, val public: Boolean = false)
data class BatteryForecast(val battery: Int, val per_hour: Double, val hours_left: Double?, val empty_at: String? = null, val text: String)
data class TripPunct(val trip: String, val usual: String, val days: Int, val late_days: Int, val late_on: List<String> = emptyList())
data class WeeklyReport(val week_start: String, val days_with_data: Int, val km: Double, val sos: Int, val alerts: Int,
                        val punctuality: List<TripPunct> = emptyList(), val min_battery: Int?, val text: String)
data class HolidayReq(val start: String, val end: String? = null, val note: String? = null, val all_children: Boolean = true)
data class HolidayAnswer(val holiday: Boolean)
data class DayRow(val date: String, val label: String, val status: String, val line: String, val km: Double,
                  val places: List<String> = emptyList(), val first: String?, val last: String?)
data class TimelineItem(val time: String?, val kind: String, val title: String, val text: String)
data class DayDetail(val date: String, val summary: String, val distance_km: Double, val max_speed_kmh: Double,
                     val min_battery: Int?, val reports: Int, val first: String?, val last: String?,
                     val timeline: List<TimelineItem> = emptyList(), val path: List<LatLon> = emptyList())
data class Routine(val days: Int, val min_days: Int, val places: List<Place> = emptyList(), val trips: List<Trip> = emptyList())
data class DaySummary(val date: String, val text: String, val source: String)
data class ChatTurn(val role: String, val text: String)
/** Family screen at-a-glance (server: ai.brief) – facts only, the app writes the sentence in the app language. */
data class Brief(val device_id: String, val state: String? = null, val place: String? = null, val place_kind: String? = null,
                 val since: String? = null, val since_day: String? = null, val arrival: String? = null, val late_min: Int? = null,
                 val until: String? = null, val next: BriefNext? = null, val near: String? = null,
                 val nearest_place: BriefNear? = null, val trip: CurrentTrip? = null, val mode: String? = null,
                 val on_bus: String? = null, val battery_until: String? = null, val battery_low: Boolean? = null,
                 val alerts_today: Int? = null, val last_alert: BriefAlert? = null, val holiday: Boolean? = null,
                 val route_alerts_paused_until: String? = null)
data class BriefNext(val place: String, val at: String? = null, val leave: String? = null, val source: String? = null)
data class BriefNear(val name: String, val m: Int, val direction: String? = null)
data class BriefAlert(val time: String? = null, val kind: String? = null, val text: String? = null)

data class AskReq(val question: String, val history: List<ChatTurn> = emptyList(), val lang: String = "en")
data class AiStatus(val engine: String, val model: String?, val reachable: Boolean?, val error: String?)
data class AskRes(val answer: String, val source: String, val engine: String = "local", val model: String? = null,
                  val tools_used: List<String> = emptyList())
data class IncidentReport(val sos_id: Int, val text: String)
data class PlanInfo(val id: String, val name: String, val monthly: Int, val yearly: Int, val history_days: Int,
                    val family: Int, val features: List<String>)
data class BillingMe(val plan: String, val paid_plan: String?, val status: String, val expires_at: String?,
                     val grace_days: Int, val mode: String)
data class SubscribeReq(val plan: String, val period: String)
data class SubscribeRes(val mode: String, val payment_id: Int, val amount_inr: Int, val checkout_url: String? = null)
data class ReportReq(val user_id: Int, val sos_id: Int?, val reason: String)
data class ForgotReq(val email: String)
data class ForgotRes(val ok: Boolean, val message: String, val dev_code: String? = null, val phone_hint: String? = null)
data class ResetReq(val email: String, val code: String, val new_password: String)
data class JoinSchoolReq(val staff_code: String, val role: String = "teacher")
data class LinkSchoolReq(val parent_code: String, val class_name: String?, val share_sos: Boolean = true)
data class SchoolSos(val sos_id: Int, val name: String, val lat: Double?, val lon: Double?, val speed_kmh: Double?,
                     val heading_deg: Double?, val battery: Int?, val started_at: String?, val last_seen: String?,
                     val status: String, val class_name: String?, val school_alerted: Boolean = false,
                     val plan: String = "basic", val group_allowed: Boolean = false, val group_started: Boolean = false)

interface SelfXApi {
    @GET("api/me/export") suspend fun exportData(): okhttp3.ResponseBody
    @retrofit2.http.HTTP(method = "DELETE", path = "api/me", hasBody = true) suspend fun deleteAccount(@Body b: DeleteReq): Map<String, Any>
    @POST("api/auth/register") suspend fun register(@Body b: RegisterReq): TokenRes
    @POST("api/auth/login") suspend fun login(@Body b: LoginReq): TokenRes
    @GET("api/devices") suspend fun devices(): List<Device>
    @GET("api/devices/{id}") suspend fun device(@Path("id") id: String): Device
    @GET("api/devices/{id}/history") suspend fun history(@Path("id") id: String, @Query("hours") hours: Int = 24, @Query("today") today: Boolean? = null): List<Point>
    @GET("api/devices/{id}/insights") suspend fun insights(@Path("id") id: String): Insights
    @GET("api/devices/{id}/summary") suspend fun summary(@Path("id") id: String, @retrofit2.http.Query("day") day: String?): DaySummary
    @GET("api/devices/{id}/days") suspend fun days(@Path("id") id: String, @retrofit2.http.Query("start") start: String? = null,
                                                   @retrofit2.http.Query("end") end: String? = null): List<DayRow>
    @GET("api/devices/{id}/day") suspend fun day(@Path("id") id: String, @retrofit2.http.Query("day") day: String): DayDetail
    @GET("api/devices/{id}/holidays") suspend fun holidays(@Path("id") id: String): List<HolidayItem>
    @POST("api/devices/{id}/holidays") suspend fun addHolidays(@Path("id") id: String, @Body b: HolidayReq): List<HolidayItem>
    @DELETE("api/devices/{id}/holidays/{day}") suspend fun deleteHoliday(@Path("id") id: String, @Path("day") day: String): List<HolidayItem>
    @POST("api/devices/{id}/holiday-answer") suspend fun holidayAnswer(@Path("id") id: String, @Body b: HolidayAnswer): Map<String, Any>
    @GET("api/devices/{id}/buses") suspend fun buses(@Path("id") id: String): List<BusItem>
    @POST("api/devices/{id}/buses") suspend fun addBus(@Path("id") id: String, @Body b: BusReq): List<BusItem>
    @DELETE("api/devices/{id}/buses/{bid}") suspend fun removeBus(@Path("id") id: String, @Path("bid") bid: Int): List<BusItem>
    @GET("api/devices/{id}/care") suspend fun care(@Path("id") id: String): Care
    @PUT("api/devices/{id}/care") suspend fun setCare(@Path("id") id: String, @Body b: CareReq): Care
    @GET("api/devices/{id}/weekly") suspend fun weekly(@Path("id") id: String): WeeklyReport
    @PUT("api/devices/{id}/family/{phone}/role") suspend fun setRole(@Path("id") id: String, @Path("phone") phone: String, @Body b: RoleReq): ChildSetup
    @GET("api/devices/{id}/routine") suspend fun routine(@Path("id") id: String): Routine
    @GET("api/ai/status") suspend fun aiStatus(): AiStatus
    @GET("api/family/brief") suspend fun familyBrief(): List<Brief>
    @POST("api/devices/{id}/ask") suspend fun ask(@Path("id") id: String, @Body b: AskReq): AskRes
    @POST("api/devices/{id}/learn") suspend fun learn(@Path("id") id: String): Map<String, Any>
    @GET("api/sos/{id}/report") suspend fun report(@Path("id") id: Int): IncidentReport
    @GET("api/plans") suspend fun plans(): List<PlanInfo>
    @GET("api/billing/me") suspend fun billing(): BillingMe
    @POST("api/billing/subscribe") suspend fun subscribe(@Body b: SubscribeReq): SubscribeRes
    @POST("api/billing/dev-confirm/{id}") suspend fun devConfirm(@Path("id") id: Int): BillingMe
    @POST("api/billing/cancel") suspend fun cancelPlan(): BillingMe
    @GET("api/staff/board") suspend fun staffBoard(): StaffBoard
    @POST("api/staff/sos/{id}/acknowledge") suspend fun staffAck(@Path("id") id: Int): Map<String, Any>
    @GET("api/staff/sos/{id}/track") suspend fun staffTrack(@Path("id") id: Int): StaffTrack
    @POST("api/staff/sos/{id}/group") suspend fun staffGroup(@Path("id") id: Int): Map<String, Any>
    @POST("api/devices/{id}/family-invites") suspend fun inviteFamily(@Path("id") id: String, @Body b: InviteReq): ChildSetup
    @POST("api/devices/{id}/family-invites/{iid}/accept") suspend fun acceptFamily(@Path("id") id: String, @Path("iid") iid: Int): ChildSetup
    @DELETE("api/devices/{id}/family-invites/{iid}") suspend fun cancelFamily(@Path("id") id: String, @Path("iid") iid: Int): ChildSetup
    @GET("api/my-schools") suspend fun mySchools(): List<MySchool>
    @DELETE("api/devices/{id}/family/{phone}") suspend fun removeFamily(@Path("id") id: String, @Path("phone") phone: String): ChildSetup
    @GET("api/devices/{id}/setup") suspend fun setup(@Path("id") id: String): ChildSetup
    @PUT("api/devices/{id}/setup") suspend fun saveSetup(@Path("id") id: String, @Body b: SetupReq): ChildSetup
    @DELETE("api/devices/{id}/school/{sid}") suspend fun unlinkSchool(@Path("id") id: String, @Path("sid") sid: Int): Map<String, Any>
    @POST("api/devices/claim") suspend fun claim(@Body b: ClaimReq): Device
    @POST("api/devices/{id}/share") suspend fun share(@Path("id") id: String, @Body b: ShareReq): Map<String, Any>
    @GET("api/sos") suspend fun activeSos(@Query("active_only") activeOnly: Boolean = true): List<Sos>
    @POST("api/sos/{id}/acknowledge") suspend fun acknowledge(@Path("id") id: Int): Sos
    @POST("api/sos/{id}/resolve") suspend fun resolve(@Path("id") id: Int): Sos

    // Phase 2
    @POST("api/auth/fcm-token") suspend fun setFcm(@Body b: FcmReq): Map<String, Any>
    @PUT("api/auth/lang") suspend fun setLang(@Body b: LangReq): Map<String, Any>
    @GET("api/devices/{id}/places") suspend fun places(@Path("id") id: String): List<ChildPlace>
    @POST("api/devices/{id}/places") suspend fun addPlace(@Path("id") id: String, @Body b: PlaceReq): ChildPlace
    @PUT("api/devices/{id}/places/{pid}") suspend fun editPlace(@Path("id") id: String, @Path("pid") pid: Int, @Body b: PlaceReq): ChildPlace
    @DELETE("api/devices/{id}/places/{pid}") suspend fun deletePlace(@Path("id") id: String, @Path("pid") pid: Int): Map<String, Any>
    @POST("api/devices/{id}/places/{pid}/people") suspend fun addPerson(@Path("id") id: String, @Path("pid") pid: Int, @Body b: PersonReq): ChildPlace
    @DELETE("api/devices/{id}/places/{pid}/people/{cid}") suspend fun removePerson(@Path("id") id: String, @Path("pid") pid: Int, @Path("cid") cid: Int): ChildPlace
    @GET("api/devices/{id}/now") suspend fun now(@Path("id") id: String): NowInfo
    @POST("api/devices/{id}/route-ok") suspend fun routeOk(@Path("id") id: String, @Body b: RouteOkReq): RouteOkRes
    @DELETE("api/devices/{id}/route-ok") suspend fun routeResume(@Path("id") id: String): Map<String, Any>
    @GET("api/devices/{id}/transports") suspend fun transports(@Path("id") id: String): List<Transport>
    @POST("api/devices/{id}/transports") suspend fun addTransport(@Path("id") id: String, @Body b: TransportReq): List<Transport>
    @PUT("api/devices/{id}/transports/{tid}") suspend fun editTransport(@Path("id") id: String, @Path("tid") tid: Int, @Body b: TransportReq): List<Transport>
    @DELETE("api/devices/{id}/transports/{tid}") suspend fun deleteTransport(@Path("id") id: String, @Path("tid") tid: Int): List<Transport>
    @GET("api/devices/{id}/geofences") suspend fun geofences(@Path("id") id: String): List<Geofence>
    @POST("api/devices/{id}/geofences") suspend fun addGeofence(@Path("id") id: String, @Body g: Geofence): Geofence
    @DELETE("api/devices/{id}/geofences/{gid}") suspend fun deleteGeofence(@Path("id") id: String, @Path("gid") gid: Int): Map<String, Any>
    @POST("api/devices/{id}/share-links") suspend fun createLink(@Path("id") id: String, @Body b: ShareLinkReq): ShareLink
    @GET("api/devices/{id}/share-links") suspend fun links(@Path("id") id: String): List<ShareLink>
    @POST("api/share-links/{token}/stop") suspend fun stopLink(@Path("token") token: String): Map<String, Any>
    @GET("api/schools") suspend fun schools(): List<School>
    @POST("api/schools") suspend fun createSchool(@Body b: SchoolReq): School
    @POST("api/schools/join") suspend fun joinSchool(@Body b: JoinSchoolReq): School
    @POST("api/devices/{id}/school") suspend fun linkSchool(@Path("id") id: String, @Body b: LinkSchoolReq): School
    @GET("api/schools/{id}/sos") suspend fun schoolSos(@Path("id") id: Int): List<SchoolSos>
    @GET("api/schools/{id}/staff") suspend fun staff(@Path("id") id: Int): List<Staff>
    @POST("api/schools/{id}/staff/{uid}/approve") suspend fun approveStaff(@Path("id") id: Int, @Path("uid") uid: Int): Staff
    @DELETE("api/schools/{id}/staff/{uid}") suspend fun removeStaff(@Path("id") id: Int, @Path("uid") uid: Int): Map<String, Any>
    @GET("api/auth/me") suspend fun me(): Me
    @POST("api/auth/otp/request") suspend fun requestOtp(@Body b: OtpReq): OtpRes
    @POST("api/auth/otp/verify") suspend fun verifyOtp(@Body b: OtpVerifyReq): Me

    // Phase 3
    @POST("api/devices/{id}/emergency") suspend fun emergency(@Path("id") id: String, @Body b: EmergencyReq): EmergencyRes
    @GET("api/sos/{id}/status") suspend fun sosStatus(@Path("id") id: Int): SosStatus
    @GET("api/devices/{id}/teacher-contacts") suspend fun contacts(@Path("id") id: String): List<TeacherContact>
    @POST("api/devices/{id}/teacher-contacts") suspend fun addContact(@Path("id") id: String, @Body c: TeacherContact): TeacherContact
    @DELETE("api/devices/{id}/teacher-contacts/{cid}") suspend fun deleteContact(@Path("id") id: String, @Path("cid") cid: Int): Map<String, Any>
    @POST("api/helpers/location") suspend fun helperLocation(@Body b: HelperLoc): Map<String, Any>
    @PUT("api/helpers/availability") suspend fun setAvailability(@Body b: Availability): Availability
    @GET("api/help/{id}") suspend fun help(@Path("id") id: Int): HelpDetail
    @POST("api/help/{id}/accept") suspend fun acceptHelp(@Path("id") id: Int): HelpDetail
    @POST("api/help/{id}/decline") suspend fun declineHelp(@Path("id") id: Int): Map<String, Any>
    @POST("api/reports") suspend fun report(@Body b: ReportReq): Map<String, Any>
    @POST("api/auth/password/forgot") suspend fun forgot(@Body b: ForgotReq): ForgotRes
    @POST("api/auth/password/reset") suspend fun reset(@Body b: ResetReq): Map<String, Any>
    @POST("api/auth/logout") suspend fun logout(): Map<String, Any>
    @POST("api/schools/{sid}/sos/{id}/group") suspend fun schoolGroup(@Path("sid") sid: Int, @Path("id") id: Int): Map<String, Any>
}

object Api {
    lateinit var session: Session
    @Volatile private var cached: SelfXApi? = null

    val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .pingInterval(25, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val t = session.token
                val req = if (t != null) chain.request().newBuilder().header("Authorization", "Bearer $t").build()
                else chain.request()
                chain.proceed(req)
            }.build()
    }

    val api: SelfXApi
        get() = cached ?: Retrofit.Builder()
            .baseUrl(session.server.trimEnd('/') + "/")
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build().create(SelfXApi::class.java).also { cached = it }

    fun reset() { cached = null }
}

/** Turns a Retrofit/HTTP error into a short message for the UI. */
fun Throwable.userMessage(): String = when (this) {
    is retrofit2.HttpException -> response()?.errorBody()?.string()?.let {
        Regex("\"detail\"\\s*:\\s*\"([^\"]+)\"").find(it)?.groupValues?.get(1)
    } ?: com.selfxtrack.app.i18n.t("Server error ({0})", code())
    is java.io.IOException -> com.selfxtrack.app.i18n.t("Cannot reach server. Check internet / server address.")
    else -> message ?: com.selfxtrack.app.i18n.t("Something went wrong")
}
