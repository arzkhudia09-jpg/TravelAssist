package `in`.travelassist.app

import android.Manifest
import android.content.pm.PackageManager
import android.location.Location
import android.os.Bundle
import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.Priority
import `in`.travelassist.app.data.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import kotlinx.coroutines.CancellationException
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.UUID

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val client = ApiClient(applicationContext, BuildConfig.API_BASE_URL)
        val model = ViewModelProvider(this, TravelViewModel.Factory(client))[TravelViewModel::class.java]
        setContent { TravelAssistApp(model) }
    }
}

data class ScreenState(
    val user: UserDto? = null,
    val trips: List<TripDto> = emptyList(),
    val savedRoutes: List<SavedRouteDto> = emptyList(),
    val dashboard: Map<String, Any>? = null,
    val integrationCatalog: Map<String, Any>? = null,
    val addons: List<Map<String, Any>> = emptyList(),
    val activeTrip: TripDto? = null,
    val members: List<MemberDto> = emptyList(),
    val itinerary: List<ItineraryDto> = emptyList(),
    val invitations: List<Map<String, Any>> = emptyList(),
    val locations: List<LocationDto> = emptyList(),
    val expenses: List<ExpenseDto> = emptyList(),
    val routeResult: Map<String, Any>? = null,
    val recoveryResult: Map<String, Any>? = null,
    val stayResult: Map<String, Any>? = null,
    val assistantContext: Map<String, Any>? = null,
    val settlements: Map<String, Any>? = null,
    val chat: List<String> = emptyList(),
    val error: String? = null,
    val busy: Boolean = false,
)

class TravelViewModel(private val client: ApiClient) : ViewModel() {
    private val _state = MutableStateFlow(ScreenState())
    val state = _state.asStateFlow()
    val apiBaseUrl: String get() = client.apiBaseUrl
    private var socket: WebSocket? = null
    private var locationClient: com.google.android.gms.location.FusedLocationProviderClient? = null
    private var locationCallback: LocationCallback? = null
    private var locationTimeout: kotlinx.coroutines.Job? = null
    private var locationStartJob: kotlinx.coroutines.Job? = null
    private var locationSessionId: String? = null
    private var locationTripId: String? = null

    init {
        if (runCatching { client.vault.read() }.getOrNull() != null) {
            viewModelScope.launch { runCatching { client.api.me() }.onSuccess { _state.update { s -> s.copy(user = it) }; loadTripsData() } }
        }
    }

    fun authenticate(email: String, password: String, username: String?, register: Boolean) = action {
        val credentials = Credentials(email, password, username?.takeIf { register })
        val result = if (register) client.api.register(credentials) else client.api.login(credentials)
        client.vault.save(result.access_token)
        _state.update { it.copy(user = result.user, error = null) }
        loadTripsData()
    }

    fun configureApiBaseUrl(value: String): Boolean = try {
        client.configureBaseUrl(value)
        _state.update { it.copy(error = null) }
        true
    } catch (error: Exception) {
        showError(error.message ?: "Unable to save the API server URL")
        false
    }

    fun signOut() {
        socket?.close(1000, "Sign out")
        socket = null
        val tripId = locationTripId ?: _state.value.activeTrip?.id
        val sessionId = locationSessionId
        stopLocationUpdates()
        locationSessionId = null
        locationTripId = null
        viewModelScope.launch {
            var error: String? = null
            if (tripId != null) {
                try {
                    client.api.stopLocation(tripId, sessionId)
                } catch (failure: Exception) {
                    error = failure.message ?: "Could not confirm that location sharing stopped"
                }
            }
            client.vault.clear()
            _state.value = ScreenState(error = error)
        }
    }

    fun loadTrips() = action {
        val trips = client.api.trips()
        _state.update { it.copy(
            trips = trips,
            dashboard = client.api.dashboard(),
            invitations = client.api.invitations(),
            savedRoutes = client.api.savedRoutes(),
            integrationCatalog = client.api.integrations(),
            addons = client.api.addons(),
        ) }
        trips.firstOrNull()?.let { loadTrip(it) }
    }

    fun createTrip(name: String, destination: String) = action {
        client.api.createTrip(TripCreate(name, destination))
        loadTripsData()
    }

    fun selectTrip(trip: TripDto) = action {
        loadTrip(trip)
    }

    private suspend fun loadTripsData() {
        val trips = client.api.trips()
        _state.update { it.copy(
            trips = trips, dashboard = client.api.dashboard(),
            invitations = client.api.invitations(), savedRoutes = client.api.savedRoutes(),
            integrationCatalog = client.api.integrations(), addons = client.api.addons(),
            activeTrip = _state.value.activeTrip?.takeIf { active -> trips.any { it.id == active.id } },
        ) }
        trips.firstOrNull()?.let { loadTrip(it) }
    }

    fun configureIntegration(providerId: String, displayName: String, apiKey: String) = action {
        require(apiKey.isNotBlank()) { "Enter the provider credential" }
        client.api.configureIntegration(mapOf(
            "provider_id" to providerId,
            "display_name" to displayName,
            "credentials" to mapOf("api_key" to apiKey),
        ))
        _state.update { it.copy(integrationCatalog = client.api.integrations()) }
    }

    fun testIntegration(integrationId: String) = action {
        val result = client.api.testIntegration(integrationId)
        _state.update { it.copy(integrationCatalog = client.api.integrations()) }
        result["diagnostic"]?.toString()?.takeIf { it.isNotBlank() }?.let(::showError)
    }

    fun setIntegrationEnabled(integrationId: String, enabled: Boolean) = action {
        client.api.setIntegrationEnabled(integrationId, mapOf("enabled" to enabled))
        _state.update { it.copy(integrationCatalog = client.api.integrations()) }
    }

    fun removeIntegration(integrationId: String) = action {
        client.api.removeIntegration(integrationId)
        _state.update { it.copy(integrationCatalog = client.api.integrations()) }
    }

    fun setAddon(addonId: String, enabled: Boolean) = action {
        client.api.setAddon(addonId, mapOf("enabled" to enabled))
        _state.update { it.copy(addons = client.api.addons()) }
    }

    fun refreshIntegrationCenter() = action {
        _state.update { it.copy(integrationCatalog = client.api.integrations(), addons = client.api.addons()) }
    }

    private suspend fun loadTrip(trip: TripDto) {
        val detail = client.api.trip(trip.id)
        _state.update { it.copy(
            activeTrip = trip, members = detail.members, itinerary = detail.itinerary,
            expenses = client.api.expenses(trip.id), locations = client.api.locations(trip.id),
            settlements = client.api.settlements(trip.id),
        ) }
    }

    fun search(source: String, destination: String, preference: String = "balanced", budget: Double? = null) = action {
        _state.update { it.copy(routeResult = client.api.searchRoutes(RouteRequest(source, destination, preference, budget))) }
    }

    fun saveRoute(source: String, destination: String, result: Map<String, Any>) = action {
        client.api.saveRoute(mapOf("source" to source, "destination" to destination, "result" to result))
        _state.update { it.copy(savedRoutes = client.api.savedRoutes()) }
    }

    fun loadAssistantContext() = action {
        val trip = requireNotNull(_state.value.activeTrip) { "Select a trip first" }
        _state.update { it.copy(assistantContext = client.api.assistantContext(trip.id)) }
    }

    fun deleteSavedRoute(id: String) = action {
        client.api.deleteSavedRoute(id)
        _state.update { it.copy(savedRoutes = client.api.savedRoutes()) }
    }

    fun recover(currentLocation: String, destination: String, budget: Double?) = action {
        val request = buildMap<String, Any> {
            put("source", currentLocation)
            put("current_location", currentLocation)
            put("destination", destination)
            put("preference", "balanced")
            budget?.let { put("remaining_budget", it) }
        }
        _state.update { it.copy(recoveryResult = client.api.recoverRoute(request)) }
    }

    fun searchStays(destination: String, maxPrice: String) = action {
        val body = buildMap<String, Any> {
            put("destination", destination)
            maxPrice.toDoubleOrNull()?.let { put("max_price", it) }
        }
        _state.update { it.copy(stayResult = client.api.searchStays(body)) }
    }

    fun addExpense(amount: String, description: String, category: String, payerId: String,
                   participants: List<String>, shares: Map<String, Double>?) = action {
        val trip = requireNotNull(_state.value.activeTrip) { "Create or select a trip first" }
        require(participants.isNotEmpty()) { "Select at least one expense participant" }
        client.api.addExpense(trip.id, ExpenseRequest(amount.toDouble(), description, category,
            participants, payerId, shares))
        _state.update { it.copy(expenses = client.api.expenses(trip.id), settlements = client.api.settlements(trip.id)) }
    }

    fun invite(email: String) = action {
        val trip = requireNotNull(_state.value.activeTrip) { "Select a trip first" }
        client.api.invite(trip.id, mapOf("email" to email))
    }

    fun addItinerary(title: String, details: String) = action {
        val trip = requireNotNull(_state.value.activeTrip) { "Select a trip first" }
        client.api.addItinerary(trip.id, mapOf("title" to title, "details" to details))
        _state.update { it.copy(itinerary = client.api.trip(trip.id).itinerary) }
    }

    fun acceptInvitation(id: String) = action {
        client.api.acceptInvitation(id)
        loadTripsData()
    }

    fun shareLocation(location: Location, durationMinutes: Int, sessionId: String) {
        viewModelScope.launch {
            try {
                val tripId = locationTripId ?: return@launch
                client.api.updateLocation(tripId, LocationUpdate(sessionId, location.latitude, location.longitude, durationMinutes))
                if (locationSessionId == sessionId) {
                    if (_state.value.activeTrip?.id == tripId) {
                        _state.update { it.copy(locations = client.api.locations(tripId)) }
                    }
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (locationSessionId == sessionId) showError(error.message ?: "Location update failed")
            }
        }
    }

    fun startLocationSharing(context: android.content.Context, durationMinutes: Int) {
        val trip = _state.value.activeTrip ?: return showError("Select a trip first")
        val previousTripId = locationTripId
        val previousSessionId = locationSessionId
        stopLocationUpdates()
        val sessionId = UUID.randomUUID().toString()
        locationSessionId = sessionId
        locationTripId = trip.id
        locationStartJob = viewModelScope.launch {
            try {
                if (previousTripId != null) {
                    client.api.stopLocation(previousTripId, previousSessionId)
                }
                client.api.startLocation(trip.id, LocationSharingStart(sessionId, durationMinutes))
                if (locationSessionId != sessionId) return@launch
                val fused = LocationServices.getFusedLocationProviderClient(context)
                locationClient = fused
                val callback = object : LocationCallback() {
                    override fun onLocationResult(result: LocationResult) {
                        result.lastLocation?.let { shareLocation(it, durationMinutes, sessionId) }
                    }
                }
                locationCallback = callback
                val request = LocationRequest.Builder(Priority.PRIORITY_BALANCED_POWER_ACCURACY, 15_000L)
                    .setMinUpdateIntervalMillis(10_000L)
                    .build()
                fused.requestLocationUpdates(request, callback, Looper.getMainLooper())
                    .addOnFailureListener { error ->
                        stopLocationUpdates()
                        showError(error.message ?: "Unable to start location updates")
                    }
                locationTimeout = viewModelScope.launch {
                    delay(durationMinutes * 60_000L)
                    val callbackToStop = locationCallback
                    val clientToStop = locationClient
                    locationCallback = null
                    locationClient = null
                    locationTimeout = null
                    locationSessionId = null
                    locationTripId = null
                    callbackToStop?.let { clientToStop?.removeLocationUpdates(it) }
                    try {
                        client.api.stopLocation(trip.id, sessionId)
                    } catch (cancelled: CancellationException) {
                        throw cancelled
                    } catch (error: Exception) {
                        showError(error.message ?: "Location share expired locally; server expiry remains active")
                    }
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (locationSessionId == sessionId) {
                    locationSessionId = null
                    locationTripId = null
                }
                showError(error.message ?: "Unable to start location sharing")
            }
        }
    }

    fun stopLocation() = action {
        val tripId = locationTripId ?: _state.value.activeTrip?.id
            ?: throw IllegalStateException("Select a trip first")
        val sessionId = locationSessionId
        stopLocationUpdates()
        locationSessionId = null
        locationTripId = null
        client.api.stopLocation(tripId, sessionId)
        if (_state.value.activeTrip?.id == tripId) {
            _state.update { it.copy(locations = client.api.locations(tripId)) }
        }
    }

    private fun stopLocationUpdates() {
        locationStartJob?.cancel()
        locationStartJob = null
        locationTimeout?.cancel()
        locationTimeout = null
        locationCallback?.let { callback -> locationClient?.removeLocationUpdates(callback) }
        locationCallback = null
        locationClient = null
    }

    fun connectChat() {
        val trip = _state.value.activeTrip ?: return showError("Select a trip first")
        socket?.close(1000, "Switch trip")
        _state.update { it.copy(chat = emptyList()) }
        socket = client.openChat(trip.id, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                val json = JSONObject(text)
                val message = json.optString("message")
                if (message.isNotBlank()) {
                    val senderId = json.optString("sender_id")
                    val sender = _state.value.members.firstOrNull { it.user_id == senderId }?.nickname ?: senderId.take(8)
                    _state.update { it.copy(chat = it.chat + "$sender: $message") }
                }
                json.optString("error").takeIf { it.isNotBlank() }?.let(::showError)
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) { showError(t.message ?: "Chat connection failed") }
        })
    }

    fun sendChat(message: String) {
        if (message.isNotBlank() && socket?.send(message) != true) showError("Chat is not connected; reconnect and retry")
    }

    private fun action(block: suspend () -> Unit) {
        viewModelScope.launch {
            _state.update { it.copy(busy = true, error = null) }
            try {
                block()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                showError(error.message ?: "Request failed")
            } finally {
                _state.update { it.copy(busy = false) }
            }
        }
    }

    private fun showError(message: String) { _state.update { it.copy(error = message) } }

    class Factory(private val client: ApiClient) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = TravelViewModel(client) as T
    }

    override fun onCleared() {
        stopLocationUpdates()
        socket?.close(1000, "App closed")
        super.onCleared()
    }
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun TravelAssistApp(model: TravelViewModel) {
    val state by model.state.collectAsStateWithLifecycle()
    var screen by remember { mutableStateOf("Trips") }
    MaterialTheme(colorScheme = if (androidx.compose.foundation.isSystemInDarkTheme()) darkColorScheme() else lightColorScheme()) {
        Surface(Modifier.fillMaxSize()) {
            if (state.user == null) {
                AuthScreen(state.busy, state.error, model.apiBaseUrl, model::configureApiBaseUrl, model::authenticate)
            } else {
                Scaffold(
                    topBar = { TopAppBar(title = { Text("Travel Assist") }) },
                    bottomBar = {
                        NavigationBar {
                            listOf("Trips", "Discover", "Expenses", "Trip tools", "Profile").forEach { label ->
                                NavigationBarItem(
                                    selected = screen == label, onClick = { screen = label },
                                    icon = { Icon(when (label) {
                                        "Discover" -> Icons.Default.Explore
                                        "Expenses" -> Icons.Default.Payments
                                        "Trip tools" -> Icons.Default.Group
                                        "Profile" -> Icons.Default.Person
                                        else -> Icons.Default.Luggage
                                    }, contentDescription = label) }, label = { Text(label) },
                                )
                            }
                        }
                    },
                ) { padding ->
                    Column(Modifier.fillMaxSize().padding(padding).padding(16.dp).verticalScroll(rememberScrollState())) {
                        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                        when (screen) {
                            "Discover" -> DiscoverScreen(state, model)
                            "Expenses" -> ExpenseScreen(state, model)
                            "Trip tools" -> TripToolsScreen(state, model)
                            "Profile" -> ProfileScreen(state, model) {
                                screen = "Integrations"
                                model.refreshIntegrationCenter()
                            }
                            "Integrations" -> IntegrationsScreen(state, model)
                            else -> TripsScreen(state, model)
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun AuthScreen(
    busy: Boolean,
    error: String?,
    apiBaseUrl: String,
    configureApiBaseUrl: (String) -> Boolean,
    authenticate: (String, String, String?, Boolean) -> Unit,
) {
    var register by remember { mutableStateOf(false) }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var username by remember { mutableStateOf("") }
    var serverUrl by remember(apiBaseUrl) { mutableStateOf(apiBaseUrl) }
    Column(
        Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Travel Assist", style = MaterialTheme.typography.headlineLarge)
        Text("Plan together. Travel confidently.", style = MaterialTheme.typography.bodyLarge)
        Spacer(Modifier.height(24.dp))
        OutlinedTextField(
            serverUrl, { serverUrl = it }, label = { Text("API server URL") },
            placeholder = { Text("https://api.example.com/") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            singleLine = true, modifier = Modifier.fillMaxWidth(),
        )
        Text("Set this to your deployed backend before signing in.", style = MaterialTheme.typography.bodySmall)
        OutlinedButton(
            onClick = { configureApiBaseUrl(serverUrl) },
            enabled = !busy && serverUrl.isNotBlank(), modifier = Modifier.fillMaxWidth(),
        ) { Text("Save server") }
        if (register) TextField(username, { username = it }, label = { Text("Username (optional)") }, modifier = Modifier.fillMaxWidth())
        TextField(email, { email = it }, label = { Text("Email") }, modifier = Modifier.fillMaxWidth())
        TextField(password, { password = it }, label = { Text("Password (10+ characters)") },
            visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Button(onClick = { authenticate(email.trim(), password, username.trim().takeIf { it.isNotBlank() }, register) },
            enabled = !busy && email.isNotBlank() && password.length >= 10, modifier = Modifier.fillMaxWidth()) {
            Text(if (register) "Create account" else "Sign in")
        }
        TextButton(onClick = { register = !register }) {
            Text(if (register) "Already have an account? Sign in" else "Create an account")
        }
    }
}

@Composable
fun TripsScreen(state: ScreenState, model: TravelViewModel) {
    var name by remember { mutableStateOf("") }
    var destination by remember { mutableStateOf("") }
    Text("Your trips", style = MaterialTheme.typography.headlineMedium)
    state.dashboard?.let { dashboard ->
        val upcoming = (dashboard["upcoming"] as? List<*>)?.size ?: 0
        val ongoing = (dashboard["ongoing"] as? List<*>)?.size ?: 0
        val completed = (dashboard["completed"] as? List<*>)?.size ?: 0
        Text("$upcoming upcoming · $ongoing ongoing · $completed completed")
        Text("${state.invitations.size} pending invitations")
    }
    if (state.trips.isEmpty()) Text("No trips yet. Create a solo or group trip to get started.")
    Spacer(Modifier.height(10.dp))
    OutlinedTextField(name, { name = it }, label = { Text("Trip name") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(destination, { destination = it }, label = { Text("Destination") }, modifier = Modifier.fillMaxWidth())
    Button(onClick = { model.createTrip(name, destination); name = ""; destination = "" },
        enabled = name.isNotBlank() && destination.isNotBlank()) { Text("Create trip") }
    Column {
        state.trips.forEach { trip ->
            Card(onClick = { model.selectTrip(trip) }, modifier = Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
                Column(Modifier.padding(14.dp)) {
                    Text(trip.name, style = MaterialTheme.typography.titleMedium)
                    Text(trip.destination)
                    if (state.activeTrip?.id == trip.id) Text("Selected trip", color = MaterialTheme.colorScheme.primary)
                }
            }
        }
        Text("Saved routes", style = MaterialTheme.typography.titleLarge)
        state.savedRoutes.forEach { route ->
            ListItem(
                headlineContent = { Text("${route.source} → ${route.destination}") },
                trailingContent = { TextButton(onClick = { model.deleteSavedRoute(route.id) }) { Text("Remove") } },
            )
        }
    }
}

@Composable
fun DiscoverScreen(state: ScreenState, model: TravelViewModel) {
    var source by remember { mutableStateOf("") }
    var destination by remember { mutableStateOf("") }
    var maxPrice by remember { mutableStateOf("") }
    var currentLocation by remember { mutableStateOf("") }
    var budget by remember { mutableStateOf("") }
    var preference by remember { mutableStateOf("balanced") }
    Text("Discover", style = MaterialTheme.typography.headlineMedium)
    OutlinedTextField(source, { source = it }, label = { Text("From") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(destination, { destination = it }, label = { Text("To / destination") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(budget, { value ->
        val text = value.filter { c -> c.isDigit() || c == '.' }
        budget = if (text.count { it == '.' } <= 1) text
        else text.substringBefore('.') + "." + text.substringAfter('.').replace(".", "")
    },
        label = { Text("Journey budget (INR, optional)") },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.fillMaxWidth())
    Row {
        listOf("cheapest", "fastest", "balanced").forEach { option ->
            FilterChip(selected = preference == option, onClick = { preference = option }, label = { Text(option) })
        }
    }
    Button(onClick = { model.search(source, destination, preference, budget.toDoubleOrNull()) },
        enabled = source.length > 1 && destination.length > 1
            && (budget.isBlank() || (budget.toDoubleOrNull()?.let { it > 0 } == true))) {
        Text("Compare routes")
    }
    OutlinedTextField(currentLocation, { currentLocation = it }, label = { Text("Current location (for recovery)") },
        modifier = Modifier.fillMaxWidth())
    Button(onClick = { model.recover(currentLocation, destination, budget.toDoubleOrNull()) },
        enabled = currentLocation.length > 1 && destination.length > 1) { Text("Find recovery options") }
    Button(onClick = { model.searchStays(destination, maxPrice) }, enabled = destination.length > 1) {
        Text("Find stays")
    }
    OutlinedTextField(maxPrice, { maxPrice = it }, label = { Text("Stay budget (INR, optional)") },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.fillMaxWidth())
    state.routeResult?.let {
        DataCard("Route results", it)
        Button(onClick = { model.saveRoute(source, destination, it) }, enabled = source.length > 1 && destination.length > 1) {
            Text("Save this route search")
        }
    }
    state.recoveryResult?.let { DataCard("Recovery options", it) }
    state.stayResult?.let { DataCard("Accommodation results", it) }
}

@Composable
fun ExpenseScreen(state: ScreenState, model: TravelViewModel) {
    var amount by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("travel") }
    var equalSplit by remember { mutableStateOf(true) }
    var selectedIds by remember(state.members) { mutableStateOf(state.members.map { it.user_id }.toSet()) }
    var payerId by remember(state.user?.id, state.members) { mutableStateOf(state.user?.id.orEmpty()) }
    val customShares = remember(state.members) { mutableStateMapOf<String, String>() }
    val shareTotal = selectedIds.sumOf { customShares[it]?.toDoubleOrNull() ?: 0.0 }
    val amountValue = amount.toDoubleOrNull()
    val sharesValid = equalSplit || (
        selectedIds.all { customShares[it]?.toDoubleOrNull() != null }
            && amountValue != null && kotlin.math.abs(shareTotal - amountValue) < 0.01
        )
    Text("Shared expenses", style = MaterialTheme.typography.headlineMedium)
    Text(state.activeTrip?.let { "Trip: ${it.name}" } ?: "Select a trip in Trips")
    OutlinedTextField(amount, { amount = it }, label = { Text("Amount (INR)") },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.fillMaxWidth())
    OutlinedTextField(description, { description = it }, label = { Text("Description") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(category, { category = it }, label = { Text("Category") }, modifier = Modifier.fillMaxWidth())
    Text("Paid by")
    Row {
        state.members.forEach { member ->
            FilterChip(selected = payerId == member.user_id, onClick = { payerId = member.user_id },
                label = { Text(member.nickname) })
        }
    }
    Text("Split between")
    state.members.forEach { member ->
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Checkbox(checked = member.user_id in selectedIds, onCheckedChange = { checked ->
                selectedIds = if (checked) selectedIds + member.user_id else selectedIds - member.user_id
            })
            Text(member.nickname, Modifier.weight(1f))
            if (!equalSplit && member.user_id in selectedIds) {
                OutlinedTextField(
                    customShares[member.user_id].orEmpty(),
                    { customShares[member.user_id] = it },
                    label = { Text("INR") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.width(110.dp),
                )
            }
        }
    }
    Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        Text("Split equally")
        Switch(checked = equalSplit, onCheckedChange = { equalSplit = it })
    }
    Button(onClick = {
        val shares = if (equalSplit) null else selectedIds.associateWith { customShares[it]?.toDoubleOrNull() ?: 0.0 }
        model.addExpense(amount, description, category, payerId, selectedIds.toList(), shares)
        amount = ""; description = ""
    },
        enabled = state.activeTrip != null && amountValue != null && amountValue > 0
            && description.isNotBlank() && selectedIds.isNotEmpty() && payerId.isNotBlank() && sharesValid) {
        Text("Add expense")
    }
    state.expenses.forEach { expense ->
        ListItem(headlineContent = { Text(expense.description) }, supportingContent = { Text(expense.category) },
            trailingContent = { Text("₹${"%.2f".format(expense.amount)}") })
    }
    state.settlements?.let { DataCard("Balances and suggested settlements", it) }
}

@Composable
fun TripToolsScreen(state: ScreenState, model: TravelViewModel) {
    val context = LocalContext.current
    var message by remember { mutableStateOf("") }
    var locationInfo by remember { mutableStateOf("") }
    var inviteEmail by remember { mutableStateOf("") }
    var itineraryTitle by remember { mutableStateOf("") }
    var itineraryDetails by remember { mutableStateOf("") }
    var duration by remember { mutableStateOf("60") }
    val uriHandler = LocalUriHandler.current
    val durationMinutes = duration.toIntOrNull()?.takeIf { it in 1..1440 }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        if (grants.values.any { it }) model.startLocationSharing(context, durationMinutes ?: 60)
        else locationInfo = "Location permission was denied."
    }
    Text("Trip tools", style = MaterialTheme.typography.headlineMedium)
    Text(state.activeTrip?.let { "Selected: ${it.name}" } ?: "Select a trip first")
    Text("Members: ${state.members.joinToString { it.nickname }}")
    OutlinedTextField(inviteEmail, { inviteEmail = it }, label = { Text("Invite by email") }, modifier = Modifier.fillMaxWidth())
    Button(onClick = { model.invite(inviteEmail); inviteEmail = "" },
        enabled = state.activeTrip != null && inviteEmail.contains("@")) { Text("Send invitation") }
    state.invitations.forEach { invitation ->
        Row {
            Text("Trip invitation: ${invitation["trip_name"] ?: "Trip"}")
            TextButton(onClick = { model.acceptInvitation(invitation["id"].toString()) }) { Text("Accept") }
        }
    }
    OutlinedTextField(itineraryTitle, { itineraryTitle = it }, label = { Text("Itinerary item") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(itineraryDetails, { itineraryDetails = it }, label = { Text("Details") }, modifier = Modifier.fillMaxWidth())
    Button(onClick = { model.addItinerary(itineraryTitle, itineraryDetails); itineraryTitle = ""; itineraryDetails = "" },
        enabled = state.activeTrip != null && itineraryTitle.isNotBlank()) { Text("Add to shared itinerary") }
    state.itinerary.forEach { Text("• ${it.title}${if (it.details.isNotBlank()) ": ${it.details}" else ""}") }
    Button(onClick = model::loadAssistantContext, enabled = state.activeTrip != null) {
        Text("Load context for future trip assistant")
    }
    state.assistantContext?.let { DataCard("Stored trip context (AI provider not configured)", it) }
    OutlinedTextField(message, { message = it }, label = { Text("Message") }, modifier = Modifier.fillMaxWidth())
    Row {
        Button(onClick = model::connectChat, enabled = state.activeTrip != null) { Text("Connect chat") }
        Button(onClick = { model.sendChat(message); message = "" }) { Text("Send") }
    }
    state.chat.forEach { Text(it, Modifier.padding(vertical = 4.dp)) }
    OutlinedTextField(duration, { duration = it.filter(Char::isDigit).take(4) },
        label = { Text("Sharing duration in minutes (1–1440)") },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth())
    Button(onClick = {
        val fine = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val coarse = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        if (fine || coarse) model.startLocationSharing(context, durationMinutes ?: 60)
        else permission.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
    }, enabled = state.activeTrip != null && durationMinutes != null) { Text("Share live location") }
    Text("Updates about every 15 seconds while the app is running; sharing expires automatically.")
    Button(onClick = { model.stopLocation() }, enabled = state.activeTrip != null) { Text("Stop sharing location now") }
    state.locations.forEach { share ->
        TextButton(onClick = { uriHandler.openUri("geo:${share.latitude},${share.longitude}?q=${share.latitude},${share.longitude}") }) {
            Text("${share.user_id.take(8)} · ${"%.5f".format(share.latitude)}, ${"%.5f".format(share.longitude)} · ${share.updated_at}")
        }
    }
    Text(locationInfo)
}

@Composable
fun ProfileScreen(state: ScreenState, model: TravelViewModel, onIntegrations: () -> Unit) {
    Text("Profile", style = MaterialTheme.typography.headlineMedium)
    Text(state.user?.username.orEmpty())
    Text(state.user?.email.orEmpty())
    Button(onClick = onIntegrations) { Text("Integrations & Add-ons") }
    Button(onClick = model::signOut) { Text("Sign out") }
}

@Composable
fun IntegrationsScreen(state: ScreenState, model: TravelViewModel) {
    val catalog = state.integrationCatalog
    val providers = (catalog?.get("integrations") as? List<*>)
        ?.mapNotNull { it as? Map<*, *> }.orEmpty()
    val isAdmin = catalog?.get("is_admin") as? Boolean ?: false
    var query by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("all") }
    var selectedProvider by remember { mutableStateOf("") }
    var displayName by remember { mutableStateOf("") }
    var credential by remember { mutableStateOf("") }
    val categories = listOf("all", "transport", "maps", "accommodation", "ai")

    Text("Integrations & Add-ons", style = MaterialTheme.typography.headlineMedium)
    Text(
        if (isAdmin) "Administrator provider settings. Credentials are encrypted on the backend."
        else "Browse supported providers and manage your personal add-ons."
    )
    OutlinedTextField(query, { query = it }, label = { Text("Search integrations") }, modifier = Modifier.fillMaxWidth())
    Row {
        categories.forEach { option ->
            FilterChip(selected = category == option, onClick = { category = option }, label = { Text(option) })
        }
    }
    providers.filter { provider ->
        val name = provider["name"]?.toString().orEmpty()
        val description = provider["description"]?.toString().orEmpty()
        (category == "all" || provider["category"]?.toString() == category)
            && (query.isBlank() || name.contains(query, true) || description.contains(query, true))
    }.forEach { provider ->
        val id = provider["id"]?.toString().orEmpty()
        Card(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
            Column(Modifier.padding(12.dp)) {
                Text(provider["name"]?.toString().orEmpty(), style = MaterialTheme.typography.titleMedium)
                Text(provider["category"]?.toString().orEmpty())
                Text(provider["description"]?.toString().orEmpty())
                (provider["features"] as? List<*>)?.joinToString()?.takeIf { it.isNotBlank() }?.let { Text("Features: $it") }
                (provider["documentation_url"] as? String)?.let { url ->
                    val uriHandler = LocalUriHandler.current
                    TextButton(onClick = { uriHandler.openUri(url) }) { Text("Documentation") }
                }
                val configurations = (provider["configurations"] as? List<*>)
                    ?.mapNotNull { it as? Map<*, *> }.orEmpty()
                configurations.forEach { configured ->
                    val integrationId = configured["id"]?.toString().orEmpty()
                    Text("${configured["display_name"]} · ${configured["status"]}")
                    if (isAdmin) {
                        Row {
                            TextButton(onClick = { model.testIntegration(integrationId) }) { Text("Test connection") }
                            TextButton(onClick = { model.removeIntegration(integrationId) }) { Text("Disconnect") }
                        }
                        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                            Text("Enabled")
                            Switch(
                                checked = configured["enabled"] as? Boolean ?: false,
                                onCheckedChange = { model.setIntegrationEnabled(integrationId, it) },
                            )
                        }
                        configured["last_error"]?.toString()?.takeIf { it.isNotBlank() }?.let {
                            Text("Diagnostic: $it", color = MaterialTheme.colorScheme.error)
                        }
                    }
                }
                if (isAdmin) {
                    TextButton(onClick = {
                        selectedProvider = id
                        displayName = provider["name"]?.toString().orEmpty()
                        credential = ""
                    }) { Text(if (selectedProvider == id) "Selected" else "Configure") }
                }
            }
        }
    }
    if (isAdmin && selectedProvider.isNotBlank()) {
        Text("Add provider configuration", style = MaterialTheme.typography.titleLarge)
        OutlinedTextField(displayName, { displayName = it }, label = { Text("Configuration name") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(credential, { credential = it }, label = { Text("Provider API credential") },
            visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
        Button(
            onClick = {
                model.configureIntegration(selectedProvider, displayName, credential)
                credential = ""
                selectedProvider = ""
            },
            enabled = displayName.isNotBlank() && credential.isNotBlank() && !state.busy,
        ) { Text("Save encrypted configuration") }
        Text("Credentials are sent only to the backend and are never returned by its APIs.")
    }

    Text("Your add-ons", style = MaterialTheme.typography.titleLarge)
    state.addons.forEach { addon ->
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.weight(1f)) {
                Text(addon["name"]?.toString().orEmpty())
                Text(addon["category"]?.toString().orEmpty(), style = MaterialTheme.typography.bodySmall)
            }
            Switch(
                checked = addon["enabled"] as? Boolean ?: false,
                onCheckedChange = { model.setAddon(addon["id"]?.toString().orEmpty(), it) },
            )
        }
    }
}

@Composable
fun DataCard(title: String, data: Map<String, Any>) {
    Card(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
        Column(Modifier.padding(12.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            data["notice"]?.let { Text(it.toString(), color = MaterialTheme.colorScheme.tertiary) }
            data["detail"]?.let { Text(it.toString(), color = MaterialTheme.colorScheme.error) }
            Text(data.toString(), style = MaterialTheme.typography.bodySmall)
        }
    }
}
