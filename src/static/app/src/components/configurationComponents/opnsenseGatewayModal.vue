<script setup>
import {ref} from "vue";
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
	keepalive: 25
})

const submitting = ref(false)
const result = ref(null)
const activeTab = ref('manual')

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
	const blob = new Blob([result.value.opnsenseConfig], {type: 'text/plain'})
	const url = URL.createObjectURL(blob)
	const a = document.createElement('a')
	a.href = url
	a.download = `${form.value.name || 'opnsense'}.conf`
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
						<small>
							Gateway peer created. IP: <strong>{{ result.assignedIP }}</strong>
						</small>
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
								<div class="col-8"><code class="text-break">{{ result.serverPublicKey }}</code>
									<i class="bi bi-clipboard ms-2" role="button" @click="copyToClipboard(result.serverPublicKey)"></i></div>
							</div>
							<div class="row g-2 mb-2">
								<div class="col-4 text-muted">Allowed IPs</div>
								<div class="col-8"><code>{{ result.tunnelNetwork }}</code>
									<i class="bi bi-clipboard ms-2" role="button" @click="copyToClipboard(result.tunnelNetwork)"></i></div>
							</div>
							<div class="row g-2 mb-2">
								<div class="col-4 text-muted">Endpoint</div>
								<div class="col-8"><code>{{ result.serverEndpoint }}:{{ result.serverPort }}</code>
									<i class="bi bi-clipboard ms-2" role="button" @click="copyToClipboard(result.serverEndpoint + ':' + result.serverPort)"></i></div>
							</div>
							<div class="row g-2">
								<div class="col-4 text-muted">Keepalive</div>
								<div class="col-8"><code>{{ result.keepalive }}</code></div>
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
								<div class="col-8"><code class="text-break">{{ result.publicKey }}</code>
									<i class="bi bi-clipboard ms-2" role="button" @click="copyToClipboard(result.publicKey)"></i></div>
							</div>
							<div class="row g-2 mb-2">
								<div class="col-4 text-muted">Private Key</div>
								<div class="col-8"><code class="text-break">{{ result.privateKey }}</code>
									<i class="bi bi-clipboard ms-2" role="button" @click="copyToClipboard(result.privateKey)"></i></div>
							</div>
							<div class="row g-2 mb-2">
								<div class="col-4 text-muted">Tunnel Address</div>
								<div class="col-8"><code>{{ result.clientTunnelAddress }}</code>
									<i class="bi bi-clipboard ms-2" role="button" @click="copyToClipboard(result.clientTunnelAddress)"></i></div>
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
						<p class="text-muted mb-2">
							<small><LocaleText t="Standard wg-quick config (for reference or wg-quick up)"></LocaleText></small>
						</p>
						<pre class="bg-body-tertiary p-3 rounded-3 border"
							 style="max-height: 300px; overflow-y: auto; font-size: 0.8rem; white-space: pre-wrap;">{{ result.opnsenseConfig }}</pre>
						<div class="d-flex gap-2">
							<button class="btn btn-sm bg-primary-subtle text-primary-emphasis rounded-3"
									@click="copyToClipboard(result.opnsenseConfig)">
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
