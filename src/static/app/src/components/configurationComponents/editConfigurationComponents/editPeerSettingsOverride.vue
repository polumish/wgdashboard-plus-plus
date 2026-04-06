<script setup lang="ts">
import LocaleText from "@/components/text/localeText.vue";
import { fetchPost } from "@/utilities/fetch.js"
import {onMounted, reactive, ref} from "vue";
const props = defineProps(['configuration'])
const saving = ref(false)
const overridePeerSettings = ref({...props.configuration.Info.OverridePeerSettings})
const edited = ref(false)
const errorMsg = ref("")
const routedLANSubnets = ref(props.configuration.Info.RoutedLANSubnets || '')
const routesSaving = ref(false)
const routesMsg = ref('')
const applying = ref(false)
const applyResult = ref(null)
const networkMode = ref(props.configuration.Info.NetworkMode || 'mesh')
const modeSaving = ref(false)

const saveNetworkMode = async () => {
	modeSaving.value = true
	await fetchPost("/api/updateWireguardConfigurationInfo", {
		Name: props.configuration.Name,
		Key: "NetworkMode",
		Value: networkMode.value
	}, (res) => {
		modeSaving.value = false
		if (res.status){
			props.configuration.Info.NetworkMode = networkMode.value
		}
	})
}

onMounted(() => {
	document.querySelectorAll("#editPeerSettingsOverride input").forEach(
		x => x.addEventListener("change", () => {
			edited.value = true
		})
	)
})

const resetForm = () => {
	overridePeerSettings.value = props.configuration.Info.OverridePeerSettings
	edited.value = false
}

const saveRoutedLANSubnets = async () => {
	routesSaving.value = true
	routesMsg.value = ''
	await fetchPost("/api/updateWireguardConfigurationInfo", {
		Name: props.configuration.Name,
		Key: "RoutedLANSubnets",
		Value: routedLANSubnets.value
	}, (res) => {
		routesSaving.value = false
		if (res.status){
			props.configuration.Info.RoutedLANSubnets = routedLANSubnets.value
			routesMsg.value = 'Saved'
		}else{
			routesMsg.value = res.message
		}
	})
}

const applyPolicyRoutes = async () => {
	applying.value = true
	applyResult.value = null
	await fetchPost(`/api/applyPolicyRoutes/${props.configuration.Name}`, {}, (res) => {
		applying.value = false
		applyResult.value = res.status ? {ok: true, data: res.data, msg: res.message} : {ok: false, msg: res.message}
	})
}

const submitForm = async () => {
	document.querySelectorAll("#editPeerSettingsOverride input").forEach(
		x => x.classList.remove("is-invalid", "is-valid")
	)
	await fetchPost("/api/updateWireguardConfigurationInfo", {
		Name: props.configuration.Name,
		Key: "OverridePeerSettings",
		Value: overridePeerSettings.value
	}, (res) => {
		if (res.status){
			edited.value = false
			props.configuration.Info.OverridePeerSettings = overridePeerSettings.value
			document.querySelectorAll("#editPeerSettingsOverride input").forEach(
				x => x.classList.add("is-valid")
			)
		}else{
			errorMsg.value = res.message
			document.querySelector(`#override_${res.data}`).classList.add("is-invalid")
		}
	})
}
</script>

<template>
<div id="editPeerSettingsOverride">
	<h5 class="mb-0">
		<i class="bi bi-diagram-3 me-2"></i>
		<LocaleText t="Network Mode"></LocaleText>
	</h5>
	<h6 class="mb-3 text-muted">
		<small><LocaleText t="Controls default AllowedIPs for new peers in this configuration"></LocaleText></small>
	</h6>
	<div class="d-flex gap-3 mb-2">
		<div class="form-check">
			<input class="form-check-input" type="radio" id="editModeMesh"
				   value="mesh" v-model="networkMode" @change="saveNetworkMode()" :disabled="modeSaving">
			<label class="form-check-label" for="editModeMesh">
				<strong><i class="bi bi-diagram-3 me-1"></i> Mesh</strong>
				<small class="text-muted d-block"><LocaleText t="Peers see each other"></LocaleText></small>
			</label>
		</div>
		<div class="form-check">
			<input class="form-check-input" type="radio" id="editModeP2S"
				   value="point-to-site" v-model="networkMode" @change="saveNetworkMode()" :disabled="modeSaving">
			<label class="form-check-label" for="editModeP2S">
				<strong><i class="bi bi-broadcast me-1"></i> Point-to-Site</strong>
				<small class="text-muted d-block"><LocaleText t="Peers see server only"></LocaleText></small>
			</label>
		</div>
		<div class="form-check">
			<input class="form-check-input" type="radio" id="editModeGW"
				   value="gateway" v-model="networkMode" @change="saveNetworkMode()" :disabled="modeSaving">
			<label class="form-check-label" for="editModeGW">
				<strong><i class="bi bi-router me-1"></i> Gateway</strong>
				<small class="text-muted d-block"><LocaleText t="Full tunnel (0.0.0.0/0)"></LocaleText></small>
			</label>
		</div>
	</div>
	<hr class="my-4">

	<h5 class="mb-0">
		<LocaleText t="Override Peer Settings"></LocaleText>
	</h5>
	<h6 class="mb-3 text-muted">
		<small>
			<LocaleText t="Only apply to peers in this configuration"></LocaleText>
		</small>
	</h6>
	<div class="d-flex gap-2 flex-column">
		<div>
			<label for="override_DNS" class="form-label">
				<small class="text-muted">
					<LocaleText t="DNS"></LocaleText>
				</small>
			</label>
			<input type="text" class="form-control form-control-sm rounded-3"
				   :disabled="saving"
				   v-model="overridePeerSettings.DNS"
				   id="override_DNS">
			<div class="invalid-feedback">{{ errorMsg }}</div>
		</div>
		<div>
			<label for="override_EndpointAllowedIPs" class="form-label">
				<small class="text-muted">
					<LocaleText t="Endpoint Allowed IPs"></LocaleText>
				</small>
			</label>
			<input type="text" class="form-control form-control-sm rounded-3"
				   :disabled="saving"
				   v-model="overridePeerSettings.EndpointAllowedIPs"
				   id="override_EndpointAllowedIPs">
			<div class="invalid-feedback">{{ errorMsg }}</div>
		</div>
		<div>
			<label for="override_ListenPort" class="form-label">
				<small class="text-muted">
					<LocaleText t="Listen Port"></LocaleText>
				</small>
			</label>
			<input type="text" class="form-control form-control-sm rounded-3"
				   :disabled="saving"
				   v-model="overridePeerSettings.ListenPort"
				   id="override_ListenPort">
			<div class="invalid-feedback">{{ errorMsg }}</div>
		</div>
		<div>
			<label for="override_MTU" class="form-label">
				<small class="text-muted">
					<LocaleText t="MTU"></LocaleText>
				</small>
			</label>
			<input type="text"
				   class="form-control form-control-sm rounded-3"
				   :disabled="saving"
				   v-model="overridePeerSettings.MTU"
				   id="override_MTU">
			<div class="invalid-feedback">{{ errorMsg }}</div>
		</div>
		<div>
			<label for="override_PeerRemoteEndpoint" class="form-label">
				<small class="text-muted">
					<LocaleText t="Peer Remote Endpoint"></LocaleText>
				</small>
			</label>
			<input type="text" class="form-control form-control-sm rounded-3"
				   :disabled="saving"
				   v-model="overridePeerSettings.PeerRemoteEndpoint"
				   id="override_PeerRemoteEndpoint">
		</div>
		<div>
			<label for="override_persistent_keepalive" class="form-label">
				<small class="text-muted">
					<LocaleText t="Persistent Keepalive"></LocaleText>
				</small>
			</label>
			<input type="text" class="form-control form-control-sm rounded-3"
				   :disabled="saving"
				   v-model="overridePeerSettings.PersistentKeepalive"
				   id="override_PersistentKeepalive">
			<div class="invalid-feedback">{{ errorMsg }}</div>
		</div>
		<div class="d-flex mt-1 gap-2">
			<button
				:class="{disabled: !edited}"
				@click="resetForm()"
				class="btn btn-sm bg-secondary-subtle border-secondary-subtle text-secondary-emphasis rounded-3 shadow ms-auto">
				<i class="bi bi-arrow-clockwise me-2"></i>
				<LocaleText t="Reset"></LocaleText>
			</button>
			<button
				:class="{disabled: !edited}"
				@click="submitForm()"
				class="btn btn-sm bg-primary-subtle border-primary-subtle text-primary-emphasis rounded-3 shadow">
				<i class="bi bi-save-fill me-2"></i>
				<LocaleText t="Save"></LocaleText>
			</button>
		</div>
	</div>

	<hr class="my-4">

	<h5 class="mb-0">
		<i class="bi bi-signpost-split me-2"></i>
		<LocaleText t="Routed LAN Subnets"></LocaleText>
	</h5>
	<h6 class="mb-3 text-muted">
		<small>
			<LocaleText t="LANs reachable via this WG interface. Installs server-side policy routing so clients of this config reach these subnets through this tunnel, regardless of what other tunnels exist."></LocaleText>
		</small>
	</h6>
	<div class="d-flex gap-2 flex-column">
		<div>
			<input type="text" class="form-control form-control-sm rounded-3"
				:disabled="routesSaving"
				v-model="routedLANSubnets"
				placeholder="e.g. 10.0.50.0/24, 10.0.54.0/24">
			<small v-if="routesMsg" class="text-muted">{{ routesMsg }}</small>
		</div>
		<div class="d-flex gap-2">
			<button @click="saveRoutedLANSubnets()"
				:disabled="routesSaving"
				class="btn btn-sm bg-primary-subtle border-primary-subtle text-primary-emphasis rounded-3 shadow">
				<i class="bi bi-save-fill me-2"></i>
				<LocaleText t="Save"></LocaleText>
			</button>
			<button @click="applyPolicyRoutes()"
				:disabled="applying"
				class="btn btn-sm bg-success-subtle border-success-subtle text-success-emphasis rounded-3 shadow ms-auto">
				<span v-if="applying" class="spinner-border spinner-border-sm me-2"></span>
				<i v-else class="bi bi-lightning-charge-fill me-2"></i>
				<LocaleText t="Apply Now"></LocaleText>
			</button>
		</div>
		<div v-if="applyResult" class="alert rounded-3 py-2 px-3 mb-0 mt-1"
			:class="applyResult.ok ? 'alert-success' : 'alert-danger'">
			<small>
				<i class="bi" :class="applyResult.ok ? 'bi-check-circle-fill' : 'bi-x-circle-fill'"></i>
				{{ applyResult.msg }}
				<span v-if="applyResult.ok && applyResult.data">
					(table {{ applyResult.data.tableId }})
				</span>
			</small>
		</div>
	</div>
</div>
</template>

<style scoped>

</style>