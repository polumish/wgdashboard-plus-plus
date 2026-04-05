<script setup>
import {ref, computed} from "vue";
import {fetchPost} from "@/utilities/fetch.js";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import LocaleText from "@/components/text/localeText.vue";
import {useRoute} from "vue-router";

const dashboardStore = DashboardConfigurationStore()
const route = useRoute()
const emits = defineEmits(['close', 'added'])

const form = ref({
	name: '',
	lan_subnets: '',
	keepalive: 25,
	all_configs: false
})

const submitting = ref(false)
const result = ref(null)
const activeTab = ref('manual')
const selectedConfigIdx = ref(0)

const results = computed(() => {
	if (!result.value) return []
	if (result.value.results) return result.value.results
	return [result.value]
})
const activeResult = computed(() => results.value[selectedConfigIdx.value] || results.value[0])

const submit = async () => {
	if (!form.value.name) {
		dashboardStore.newMessage("WGDashboard", "Please provide a name", "warning")
		return
	}
	submitting.value = true
	await fetchPost(`/api/addOPNsenseGateway/${route.params.id}`, form.value, (res) => {
		if (res.status) {
			result.value = res.data
			dashboardStore.newMessage("Server", "OPNsense gateway peer created", "success")
		} else {
			dashboardStore.newMessage("Server", res.message, "danger")
		}
		submitting.value = false
	})
}

const copyToClipboard = (text) => {
	navigator.clipboard.writeText(text).then(() => {
		dashboardStore.newMessage("WGDashboard", "Copied to clipboard", "success")
	})
}

const downloadConf = () => {
	const r = activeResult.value
	const blob = new Blob([r.opnsenseConfig], {type: 'text/plain'})
	const url = URL.createObjectURL(blob)
	const a = document.createElement('a')
	a.href = url
	const suffix = r.configName ? `_${r.configName}` : ''
	a.download = `${form.value.name || 'opnsense'}${suffix}.conf`
	a.click()
	URL.revokeObjectURL(url)
}

const close = () => {
	if (result.value) {
		emits('added')
	}
	emits('close')
}
</script>

<template>
<div class="peerSettingContainer w-100 h-100 position-absolute top-0 start-0 overflow-y-scroll">
	<div class="container d-flex h-100 w-100">
		<div class="m-auto modal-dialog-centered dashboardModal">
			<div class="card rounded-3 shadow flex-grow-1">
				<div class="card-header bg-transparent d-flex align-items-center gap-2 border-0 p-4">
					<h4 class="mb-0">
						<i class="bi bi-router me-2"></i>
						<LocaleText t="Add OPNsense Gateway"></LocaleText>
					</h4>
					<button class="btn-close ms-auto" @click="close()"></button>
				</div>

				<!-- Form (before submission) -->
				<div class="card-body px-4 pb-4" v-if="!result">
					<div class="d-flex flex-column gap-3">
						<div>
							<label class="form-label"><LocaleText t="Gateway Name"></LocaleText></label>
							<input type="text" class="form-control rounded-3"
								   v-model="form.name" placeholder="e.g. OPNsense-Proxmox1">
						</div>
						<div>
							<label class="form-label"><LocaleText t="LAN Subnets behind OPNsense"></LocaleText></label>
							<input type="text" class="form-control rounded-3"
								   v-model="form.lan_subnets" placeholder="e.g. 100.50.0.0/24, 192.168.1.0/24">
							<small class="text-muted">
								<LocaleText t="Comma-separated CIDR ranges that are reachable through this gateway"></LocaleText>
							</small>
						</div>
						<div>
							<label class="form-label"><LocaleText t="Persistent Keepalive"></LocaleText></label>
							<input type="number" class="form-control rounded-3"
								   v-model.number="form.keepalive" min="0" max="65535">
						</div>
						<div class="form-check form-switch">
							<input class="form-check-input" type="checkbox" role="switch"
								   id="allConfigsSwitch" v-model="form.all_configs">
							<label class="form-check-label" for="allConfigsSwitch">
								<LocaleText t="Add to ALL WireGuard networks"></LocaleText>
							</label>
							<div><small class="text-muted">
								<LocaleText t="Creates a separate peer with fresh keys in each WG config. OPNsense side will need one WG instance per network (full isolation between networks)."></LocaleText>
							</small></div>
						</div>
						<button class="btn btn-primary rounded-3 w-100"
								:disabled="submitting || !form.name"
								@click="submit()">
							<span v-if="submitting" class="spinner-border spinner-border-sm me-2"></span>
							{{ submitting ? 'Creating...' : 'Create Gateway Peer' }}
						</button>
					</div>
				</div>

				<!-- Result (after submission) -->
				<div class="card-body px-4 pb-4" v-else>
					<div class="alert alert-success rounded-3 d-flex align-items-center mb-3">
						<i class="bi bi-check-circle-fill me-2"></i>
						<small v-if="results.length > 1">
							Created <strong>{{ results.length }}</strong> gateway peers across all networks.
						</small>
						<small v-else>
							Gateway peer created. IP: <strong>{{ activeResult.assignedIP }}</strong>
						</small>
					</div>

					<!-- Config selector (multi-network mode) -->
					<div v-if="results.length > 1" class="mb-3">
						<label class="form-label mb-1"><small class="text-muted"><LocaleText t="Select network to view"></LocaleText></small></label>
						<select class="form-select form-select-sm rounded-3" v-model.number="selectedConfigIdx">
							<option v-for="(r, i) in results" :key="r.configName" :value="i">
								{{ r.configName }} — {{ r.assignedIP }}
							</option>
						</select>
					</div>

					<!-- Tabs -->
					<ul class="nav nav-pills mb-3 gap-1">
						<li class="nav-item">
							<a class="nav-link rounded-3" :class="{active: activeTab === 'manual'}"
							   role="button" @click="activeTab = 'manual'">
								<small>Manual Setup</small>
							</a>
						</li>
						<li class="nav-item">
							<a class="nav-link rounded-3" :class="{active: activeTab === 'config'}"
							   role="button" @click="activeTab = 'config'">
								<small>WireGuard Config</small>
							</a>
						</li>
					</ul>

					<!-- Manual Setup tab -->
					<div v-if="activeTab === 'manual'">
						<p class="text-muted mb-2">
							<small>
								<LocaleText t="Enter these values in OPNsense: VPN → WireGuard → Instances (local) and Peers (remote)"></LocaleText>
							</small>
						</p>
						<div class="alert alert-warning rounded-3 py-2 px-3 mb-3">
							<small>
								<i class="bi bi-exclamation-triangle-fill me-1"></i>
								<LocaleText t="Do NOT import an XML backup — it will overwrite your entire OPNsense configuration."></LocaleText>
							</small>
						</div>

						<h6 class="mb-2"><LocaleText t="Peer (remote WGDashboard server)"></LocaleText></h6>
						<div class="bg-body-tertiary p-3 rounded-3 border mb-3" style="font-size: 0.85rem;">
							<div class="row g-2 mb-2">
								<div class="col-4 text-muted">Name</div>
								<div class="col-8"><code>{{ form.name }}-server</code>
									<i class="bi bi-clipboard ms-2" role="button" @click="copyToClipboard(form.name + '-server')"></i></div>
							</div>
							<div class="row g-2 mb-2">
								<div class="col-4 text-muted">Public Key</div>
								<div class="col-8"><code class="text-break">{{ activeResult.serverPublicKey }}</code>
									<i class="bi bi-clipboard ms-2" role="button" @click="copyToClipboard(activeResult.serverPublicKey)"></i></div>
							</div>
							<div class="row g-2 mb-2">
								<div class="col-4 text-muted">Allowed IPs</div>
								<div class="col-8"><code>{{ activeResult.tunnelNetwork }}</code>
									<i class="bi bi-clipboard ms-2" role="button" @click="copyToClipboard(activeResult.tunnelNetwork)"></i></div>
							</div>
							<div class="row g-2 mb-2">
								<div class="col-4 text-muted">Endpoint</div>
								<div class="col-8"><code>{{ activeResult.serverEndpoint }}:{{ activeResult.serverPort }}</code>
									<i class="bi bi-clipboard ms-2" role="button" @click="copyToClipboard(activeResult.serverEndpoint + ':' + activeResult.serverPort)"></i></div>
							</div>
							<div class="row g-2">
								<div class="col-4 text-muted">Keepalive</div>
								<div class="col-8"><code>{{ activeResult.keepalive }}</code></div>
							</div>
						</div>

						<h6 class="mb-2"><LocaleText t="Instance (local OPNsense)"></LocaleText></h6>
						<div class="bg-body-tertiary p-3 rounded-3 border" style="font-size: 0.85rem;">
							<div class="row g-2 mb-2">
								<div class="col-4 text-muted">Name</div>
								<div class="col-8"><code>{{ form.name }}</code>
									<i class="bi bi-clipboard ms-2" role="button" @click="copyToClipboard(form.name)"></i></div>
							</div>
							<div class="row g-2 mb-2">
								<div class="col-4 text-muted">Public Key</div>
								<div class="col-8"><code class="text-break">{{ activeResult.publicKey }}</code>
									<i class="bi bi-clipboard ms-2" role="button" @click="copyToClipboard(activeResult.publicKey)"></i></div>
							</div>
							<div class="row g-2 mb-2">
								<div class="col-4 text-muted">Private Key</div>
								<div class="col-8"><code class="text-break">{{ activeResult.privateKey }}</code>
									<i class="bi bi-clipboard ms-2" role="button" @click="copyToClipboard(activeResult.privateKey)"></i></div>
							</div>
							<div class="row g-2 mb-2">
								<div class="col-4 text-muted">Tunnel Address</div>
								<div class="col-8"><code>{{ activeResult.clientTunnelAddress }}</code>
									<i class="bi bi-clipboard ms-2" role="button" @click="copyToClipboard(activeResult.clientTunnelAddress)"></i></div>
							</div>
							<div class="row g-2 mb-2">
								<div class="col-4 text-muted">Listen Port</div>
								<div class="col-8"><code>51820</code></div>
							</div>
							<div class="row g-2">
								<div class="col-4 text-muted">Peers</div>
								<div class="col-8"><code>{{ form.name }}-server</code></div>
							</div>
						</div>
					</div>

					<!-- Config tab -->
					<div v-if="activeTab === 'config'">
						<div class="alert alert-info rounded-3 py-2 px-3 mb-2">
							<small>
								<i class="bi bi-info-circle-fill me-1"></i>
								<LocaleText t="OPNsense 23.7+: import via VPN → WireGuard → Instances → Import (paste this config). Do NOT use System → Configuration → Backup/Restore."></LocaleText>
							</small>
						</div>
						<p class="text-muted mb-2">
							<small><LocaleText t="Standard wg-quick config — also usable with wg-quick up"></LocaleText></small>
						</p>
						<pre class="bg-body-tertiary p-3 rounded-3 border"
							 style="max-height: 300px; overflow-y: auto; font-size: 0.8rem; white-space: pre-wrap;">{{ activeResult.opnsenseConfig }}</pre>
						<div class="d-flex gap-2">
							<button class="btn btn-sm bg-primary-subtle text-primary-emphasis rounded-3"
									@click="copyToClipboard(activeResult.opnsenseConfig)">
								<i class="bi bi-clipboard me-1"></i> <LocaleText t="Copy"></LocaleText>
							</button>
							<button class="btn btn-sm bg-success-subtle text-success-emphasis rounded-3"
									@click="downloadConf()">
								<i class="bi bi-download me-1"></i> <LocaleText t="Download .conf"></LocaleText>
							</button>
						</div>
					</div>

					<hr>
					<button class="btn btn-body rounded-3 w-100" @click="close()">
						<LocaleText t="Done"></LocaleText>
					</button>
				</div>
			</div>
		</div>
	</div>
</div>
</template>

<style scoped>
*:focus { outline: none; }
</style>
