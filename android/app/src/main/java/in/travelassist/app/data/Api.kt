package `in`.travelassist.app.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.DELETE
import retrofit2.http.PATCH
import retrofit2.http.Path
import retrofit2.http.Query
import java.nio.ByteBuffer
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

data class Credentials(val email: String, val password: String, val username: String? = null)
data class UserDto(val id: String, val email: String, val username: String)
data class AuthResponse(val access_token: String, val user: UserDto)
data class TripDto(val id: String, val name: String, val destination: String, val starts_at: String? = null)
data class SavedRouteDto(val id: String, val source: String, val destination: String)
data class MemberDto(val user_id: String, val nickname: String, val role: String)
data class TripDetailDto(
    val id: String, val name: String, val destination: String, val members: List<MemberDto>,
    val itinerary: List<ItineraryDto> = emptyList(),
)
data class ItineraryDto(val id: String, val title: String, val details: String, val scheduled_at: String?)
data class LocationDto(val user_id: String, val latitude: Double, val longitude: Double, val updated_at: String, val expires_at: String)
data class LocationSharingStart(val session_id: String, val duration_minutes: Int)
data class LocationUpdate(val session_id: String, val latitude: Double, val longitude: Double, val duration_minutes: Int)
data class TripCreate(val name: String, val destination: String)
data class RouteRequest(
    val source: String,
    val destination: String,
    val preference: String = "balanced",
    val budget: Double? = null,
)
data class ExpenseRequest(
    val amount: Double,
    val description: String,
    val category: String = "other",
    val participants: List<String>,
    val payer_id: String? = null,
    val shares: Map<String, Double>? = null,
)
data class ExpenseDto(
    val id: String, val payer_id: String, val amount: Double, val description: String,
    val category: String, val participants: List<String>, val shares: Map<String, Double>,
)
data class ChatDto(val id: String, val sender_id: String, val message: String, val created_at: String)

interface TravelApi {
    @POST("api/auth/register") suspend fun register(@Body body: Credentials): AuthResponse
    @POST("api/auth/login") suspend fun login(@Body body: Credentials): AuthResponse
    @GET("api/auth/me") suspend fun me(): UserDto
    @GET("api/integrations") suspend fun integrations(): Map<String, Any>
    @POST("api/admin/integrations") suspend fun configureIntegration(@Body body: Map<String, Any>): Map<String, Any>
    @POST("api/admin/integrations/{integrationId}/test") suspend fun testIntegration(
        @Path("integrationId") integrationId: String,
    ): Map<String, Any>
    @PATCH("api/admin/integrations/{integrationId}") suspend fun setIntegrationEnabled(
        @Path("integrationId") integrationId: String, @Body body: Map<String, Boolean>,
    ): Map<String, Any>
    @DELETE("api/admin/integrations/{integrationId}") suspend fun removeIntegration(
        @Path("integrationId") integrationId: String,
    )
    @GET("api/addons") suspend fun addons(): List<Map<String, Any>>
    @PUT("api/addons/{addonId}") suspend fun setAddon(
        @Path("addonId") addonId: String, @Body body: Map<String, Boolean>,
    ): Map<String, Any>
    @GET("api/dashboard") suspend fun dashboard(): Map<String, Any>
    @GET("api/trips") suspend fun trips(): List<TripDto>
    @POST("api/trips") suspend fun createTrip(@Body body: TripCreate): TripDto
    @GET("api/saved-routes") suspend fun savedRoutes(): List<SavedRouteDto>
    @POST("api/saved-routes") suspend fun saveRoute(@Body body: Map<String, Any>): SavedRouteDto
    @DELETE("api/saved-routes/{routeId}") suspend fun deleteSavedRoute(@Path("routeId") routeId: String)
    @GET("api/trips/{tripId}") suspend fun trip(@Path("tripId") tripId: String): TripDetailDto
    @POST("api/trips/{tripId}/invitations") suspend fun invite(
        @Path("tripId") tripId: String, @Body body: Map<String, String>,
    ): Map<String, Any>
    @GET("api/invitations") suspend fun invitations(): List<Map<String, Any>>
    @POST("api/invitations/{invitationId}/accept") suspend fun acceptInvitation(
        @Path("invitationId") invitationId: String,
    ): Map<String, Any>
    @POST("api/trips/{tripId}/itinerary") suspend fun addItinerary(
        @Path("tripId") tripId: String, @Body body: Map<String, String>,
    ): ItineraryDto
    @GET("api/trips/{tripId}/assistant/context") suspend fun assistantContext(
        @Path("tripId") tripId: String,
    ): Map<String, Any>
    @POST("api/routes/search") suspend fun searchRoutes(@Body body: RouteRequest): Map<String, Any>
    @POST("api/routes/recover") suspend fun recoverRoute(@Body body: Map<String, Any>): Map<String, Any>
    @POST("api/stays/search") suspend fun searchStays(@Body body: Map<String, Any>): Map<String, Any>
    @GET("api/trips/{tripId}/expenses") suspend fun expenses(@Path("tripId") tripId: String): List<ExpenseDto>
    @POST("api/trips/{tripId}/expenses") suspend fun addExpense(
        @Path("tripId") tripId: String, @Body body: ExpenseRequest,
    ): ExpenseDto
    @GET("api/trips/{tripId}/settlements") suspend fun settlements(
        @Path("tripId") tripId: String,
    ): Map<String, Any>
    @GET("api/trips/{tripId}/locations") suspend fun locations(@Path("tripId") tripId: String): List<LocationDto>
    @POST("api/trips/{tripId}/location/me/start") suspend fun startLocation(
        @Path("tripId") tripId: String, @Body body: LocationSharingStart,
    ): Map<String, Any>
    @PUT("api/trips/{tripId}/location/me") suspend fun updateLocation(
        @Path("tripId") tripId: String, @Body body: LocationUpdate,
    ): Map<String, Any>
    @DELETE("api/trips/{tripId}/location/me") suspend fun stopLocation(
        @Path("tripId") tripId: String, @Query("session_id") sessionId: String? = null,
    )
}

class TokenVault(context: Context) {
    private val preferences = context.getSharedPreferences("secure_session", Context.MODE_PRIVATE)
    private val keyAlias = "travel-assist-session"

    fun save(token: String) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val encrypted = cipher.doFinal(token.toByteArray(Charsets.UTF_8))
        val combined = ByteBuffer.allocate(4 + cipher.iv.size + encrypted.size)
            .putInt(cipher.iv.size).put(cipher.iv).put(encrypted).array()
        check(preferences.edit().putString("token", Base64.encodeToString(combined, Base64.NO_WRAP)).commit()) {
            "Unable to save the encrypted session"
        }
    }

    fun read(): String? {
        val encoded = preferences.getString("token", null) ?: return null
        val bytes = Base64.decode(encoded, Base64.NO_WRAP)
        val buffer = ByteBuffer.wrap(bytes)
        val iv = ByteArray(buffer.int)
        buffer.get(iv)
        val encrypted = ByteArray(buffer.remaining())
        buffer.get(encrypted)
        return Cipher.getInstance("AES/GCM/NoPadding").run {
            init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
            doFinal(encrypted).toString(Charsets.UTF_8)
        }
    }

    fun clear() {
        check(preferences.edit().remove("token").commit()) { "Unable to clear the saved session" }
    }

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(keyAlias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").run {
            init(KeyGenParameterSpec.Builder(
                keyAlias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true).build())
            generateKey()
        }
    }
}

class ApiClient(context: Context, baseUrl: String) {
    val vault = TokenVault(context)
    private val preferences = context.getSharedPreferences("api_settings", Context.MODE_PRIVATE)
    @Volatile private var configuredBaseUrl = preferences.getString("base_url", null) ?: baseUrl
    private val http = OkHttpClient.Builder()
        .addInterceptor(Interceptor { chain ->
            val request = chain.request().newBuilder().apply {
                vault.read()?.let { header("Authorization", "Bearer $it") }
            }.build()
            chain.proceed(request)
        }).build()
    @Volatile var api: TravelApi = createApi(configuredBaseUrl)
        private set

    val apiBaseUrl: String get() = configuredBaseUrl

    fun configureBaseUrl(value: String) {
        val parsed = value.trim().toHttpUrlOrNull()
            ?: throw IllegalArgumentException("Enter a valid API server URL, such as https://api.example.com/")
        require(parsed.scheme == "https" || parsed.scheme == "http") {
            "The API server URL must use HTTPS or HTTP"
        }
        require(parsed.username.isEmpty() && parsed.password.isEmpty() && parsed.query == null && parsed.fragment == null) {
            "The API server URL must not contain credentials, a query, or a fragment"
        }
        val normalized = parsed.toString().let { if (it.endsWith("/")) it else "$it/" }
        val configuredApi = createApi(normalized)
        check(preferences.edit().putString("base_url", normalized).commit()) {
            "Unable to save the API server URL"
        }
        configuredBaseUrl = normalized
        api = configuredApi
    }

    private fun createApi(url: String): TravelApi = Retrofit.Builder()
        .baseUrl(url)
        .client(http)
        .addConverterFactory(GsonConverterFactory.create())
        .build().create(TravelApi::class.java)

    fun openChat(tripId: String, listener: WebSocketListener): WebSocket {
        val token = requireNotNull(vault.read()) { "Sign in before opening trip chat" }
        val webSocketBaseUrl = apiBaseUrl.replaceFirst("https://", "wss://")
            .replaceFirst("http://", "ws://")
        val url = "${webSocketBaseUrl}api/trips/$tripId/chat"
        return http.newWebSocket(Request.Builder().url(url).header("Authorization", "Bearer $token").build(), listener)
    }
}
