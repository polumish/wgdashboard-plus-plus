<script>
import {fetchPost, fetchGet} from "@/utilities/fetch.js";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import LocaleText from "@/components/text/localeText.vue";

export default {
	name: "peerSettings",
	components: {LocaleText},
	props: {
		selectedPeer: Object
	},
	data(){
		return {
			data: undefined,
			dataChanged: false,
			showKey: false,
			saving: false,
			opnsenseData: null,
			opnsenseVisible: false,
			opnsenseLoading: false
		}
	},
	setup(){
		const dashboardConfigurationStore = DashboardConfigurationStore();
		return {dashboardConfigurationStore}
	},
	methods: {
		reset(){
			if (this.selectedPeer){
				this.data = JSON.parse(JSON.stringify(this.selectedPeer))
				this.dataChanged = false;
				this.opnsenseData = null
				this.opnsenseVisible = false
			}
		},
		savePeer(){
			this.saving = true;
			fetchPost(`/api/updatePeerSettings/${this.$route.params.id}`, this.data, (res) => {
				this.saving = false;
				if (res.status){
					this.dashboardConfigurationStore.newMessage("Server", "Peer saved", "success")
				}else{
					this.dashboardConfigurationStore.newMessage("Server", res.message, "danger")
				}
				this.$emit("refresh")
			})
		},
		resetPeerData(type){
			this.saving = true
			fetchPost(`/api/resetPeerData/${this.$route.params.id}`, {
				id: this.data.id,
				type: type
			}, (res) => {
				this.saving = false;
				if (res.status){
					this.dashboardConfigurationStore.newMessage("Server", "Peer data usage reset successfully", "success")
				}else{
					this.dashboardConfigurationStore.newMessage("Server", res.message, "danger")
				}
				this.$emit("refresh")
			})
		},
		copyToClipboard(text){
			navigator.clipboard.writeText(String(text)).then(() => {
				this.dashboardConfigurationStore.newMessage("WGDashboard", "Copied to clipboard", "success")
			})
		},
		showOPNsenseSetup(){
			if (this.opnsenseVisible){
				this.opnsenseVisible = false
				return
			}
			if (this.opnsenseData){
				this.opnsenseVisible = true
				return
			}
			this.opnsenseLoading = true
			fetchGet(`/api/getOPNsenseGatewayData/${this.$route.params.id}/${encodeURIComponent(this.data.id)}`, {}, (res) => {
				this.opnsenseLoading = false
				if (res.status){
					this.opnsenseData = res.data
					this.opnsenseVisible = true
				}else{
					this.dashboardConfigurationStore.newMessage("Server", res.message, "danger")
				}
			})
		},
		toggleGateway(){
			this.saving = true
			const newVal = !this.data.is_gateway
			fetchPost(`/api/setPeerGatewayFlag/${this.$route.params.id}`, {
				id: this.data.id,
				is_gateway: newVal
			}, (res) => {
				this.saving = false
				if (res.status){
					this.data.is_gateway = newVal
					this.dashboardConfigurationStore.newMessage("Server",
						newVal ? "Peer marked as gateway" : "Gateway flag removed", "success")
					this.$emit("refresh")
				}else{
					this.dashboardConfigurationStore.newMessage("Server", res.message, "danger")
				}
			})
		}
	},
	beforeMount() {
		this.reset();
	},
	mounted() {
		this.$el.querySelectorAll("input").forEach(x => {
			x.addEventListener("change", () => {
				this.dataChanged = true;
			});
		})
	}
}
</script>

<template>
	<div class="peerSettingContainer w-100 h-100 position-absolute top-0 start-0 overflow-y-scroll">
		<div class="container d-flex h-100 w-100">
			<div class="m-auto modal-dialog-centered dashboardModal">
				<div class="card rounded-3 shadow flex-grow-1">
					<div class="card-header bg-transparent d-flex align-items-center gap-2 border-0 p-4 pb-2">
						<h4 class="mb-0">
							<LocaleText t="Peer Settings"></LocaleText>
						</h4>
						<button type="button" class="btn-close ms-auto" @click="this.$emit('close')"></button>
					</div>
					<div class="card-body px-4" v-if="this.data">
						<div class="d-flex flex-column gap-2 mb-4">
							<div class="d-flex align-items-center">
								<small class="text-muted">
									<LocaleText t="Public Key"></LocaleText>
								</small>
								<small class="ms-auto"><samp>{{this.data.id}}</samp></small>
							</div>
							<div>
								<label for="peer_name_textbox" class="form-label">
									<small class="text-muted">
										<LocaleText t="Name"></LocaleText>
									</small>
								</label>
								<input type="text" class="form-control form-control-sm rounded-3"
								       :disabled="this.saving"
								       v-model="this.data.name"
								       id="peer_name_textbox" placeholder="">
							</div>
							<div>
								<div class="d-flex position-relative">
									<label for="peer_private_key_textbox" class="form-label">
										<small class="text-muted"><LocaleText t="Private Key"></LocaleText> 
											<code>
												<LocaleText t="(Required for QR Code and Download)"></LocaleText>
											</code></small>
									</label>
									<a role="button" class="ms-auto text-decoration-none toggleShowKey"
									   @click="this.showKey = !this.showKey"
									>
										<i class="bi" :class="[this.showKey ? 'bi-eye-slash-fill':'bi-eye-fill']"></i>
									</a>
								</div>
								<input :type="[this.showKey ? 'text':'password']" class="form-control form-control-sm rounded-3"
								       :disabled="this.saving"
								       v-model="this.data.private_key"
								       id="peer_private_key_textbox"
								       style="padding-right: 40px">
							</div>
							<div>
								<label for="peer_allowed_ip_textbox" class="form-label">
									<small class="text-muted">
										<LocaleText t="Allowed IPs"></LocaleText>
										<code>
											<LocaleText t="(Required)"></LocaleText>
										</code></small>
								</label>
								<input type="text" class="form-control form-control-sm rounded-3"
								       :disabled="this.saving"
								       v-model="this.data.allowed_ip"
								       id="peer_allowed_ip_textbox">
							</div>

							<div>
								<label for="peer_endpoint_allowed_ips" class="form-label">
									<small class="text-muted">
										<LocaleText t="Endpoint Allowed IPs"></LocaleText>
										<code>
											<LocaleText t="(Required)"></LocaleText>
										</code></small>
								</label>
								<input type="text" class="form-control form-control-sm rounded-3"
								       :disabled="this.saving"
								       v-model="this.data.endpoint_allowed_ip"
								       id="peer_endpoint_allowed_ips">
							</div>
							<div>
								<label for="peer_DNS_textbox" class="form-label">
									<small class="text-muted">
										<LocaleText t="DNS"></LocaleText>
									</small>
								</label>
								<input type="text" class="form-control form-control-sm rounded-3"
								       :disabled="this.saving"
								       v-model="this.data.DNS"
								       id="peer_DNS_textbox">
							</div>
							<div class="accordion my-3" id="peerSettingsAccordion">
								<div class="accordion-item">
									<h2 class="accordion-header">
										<button class="accordion-button rounded-3 collapsed" type="button"
										        data-bs-toggle="collapse" data-bs-target="#peerSettingsAccordionOptional">
											<LocaleText t="Optional Settings"></LocaleText>
										</button>
									</h2>
									<div id="peerSettingsAccordionOptional" class="accordion-collapse collapse"
									     data-bs-parent="#peerSettingsAccordion">
										<div class="accordion-body d-flex flex-column gap-2 mb-2">
											<div>
												<label for="peer_preshared_key_textbox" class="form-label">
													<small class="text-muted">
														<LocaleText t="Pre-Shared Key"></LocaleText></small>
												</label>
												<input type="text" class="form-control form-control-sm rounded-3"
												       :disabled="this.saving"
												       v-model="this.data.preshared_key"
												       id="peer_preshared_key_textbox">
											</div>
											<div>
												<label for="peer_mtu" class="form-label"><small class="text-muted">
													<LocaleText t="MTU"></LocaleText>
												</small></label>
												<input type="number" class="form-control form-control-sm rounded-3"
												       :disabled="this.saving"
												       v-model="this.data.mtu"
												       id="peer_mtu">
											</div>
											<div>
												<label for="peer_keep_alive" class="form-label">
													<small class="text-muted">
														<LocaleText t="Persistent Keepalive"></LocaleText>
													</small>
												</label>
												<input type="number" class="form-control form-control-sm rounded-3"
												       :disabled="this.saving"
												       v-model="this.data.keepalive"
												       id="peer_keep_alive">
											</div>
										</div>
									</div>
								</div>
							</div>
							<div class="d-flex align-items-center gap-2">
								<button class="btn bg-secondary-subtle border-secondary-subtle text-secondary-emphasis rounded-3 shadow ms-auto px-3 py-2"
								        @click="this.reset()"
								        :disabled="!this.dataChanged || this.saving">
									<i class="bi bi-arrow-clockwise me-2"></i>
									<LocaleText t="Reset"></LocaleText>
								</button>

								<button class="btn bg-primary-subtle border-primary-subtle text-primary-emphasis rounded-3 px-3 py-2 shadow"
								        :disabled="!this.dataChanged || this.saving"
								        @click="this.savePeer()"
								>
									<i class="bi bi-save-fill me-2"></i>
									<LocaleText t="Save"></LocaleText>
								</button>
							</div>
							<hr>
							<div class="d-flex gap-2 align-items-center">
								<strong>
									<i class="bi bi-router me-2"></i>
									<LocaleText t="Mark as Gateway"></LocaleText>
								</strong>
								<small class="text-muted ms-2">
									<LocaleText t="Show this peer in the Gateways view"></LocaleText>
								</small>
								<div class="form-check form-switch ms-auto mb-0">
									<input class="form-check-input" type="checkbox" role="switch"
										:id="'peerGatewayToggle_' + this.data.id"
										:checked="this.data.is_gateway"
										:disabled="this.saving"
										@change="this.toggleGateway()">
								</div>
							</div>
							<div v-if="this.data.is_gateway" class="mt-2">
								<button class="btn btn-sm bg-info-subtle text-info-emphasis rounded-3 w-100"
										:disabled="this.opnsenseLoading"
										@click="this.showOPNsenseSetup()">
									<span v-if="this.opnsenseLoading" class="spinner-border spinner-border-sm me-2"></span>
									<i v-else class="bi" :class="this.opnsenseVisible ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
									<LocaleText t="Show OPNsense Setup (manual values)"></LocaleText>
								</button>
							</div>
							<div v-if="this.opnsenseVisible && this.opnsenseData" class="mt-3">
								<div class="alert alert-warning rounded-3 py-2 px-3 mb-3">
									<small>
										<i class="bi bi-exclamation-triangle-fill me-1"></i>
										<LocaleText t="Do NOT import an XML backup — enter these values manually in OPNsense."></LocaleText>
									</small>
								</div>
								<div class="d-flex align-items-center mb-2 gap-2">
									<span class="badge bg-primary rounded-circle">1</span>
									<h6 class="mb-0" style="font-size: 0.9rem;">VPN → WireGuard → Peers → <strong>Add peer</strong></h6>
								</div>
								<div class="bg-body-tertiary p-3 rounded-3 border mb-3" style="font-size: 0.8rem;">
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Enabled</div><div class="col-8"><i class="bi bi-check-square"></i></div></div>
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Name</div><div class="col-8"><code>{{ this.opnsenseData.name }}-server</code> <i class="bi bi-clipboard ms-2" role="button" @click="this.copyToClipboard(this.opnsenseData.name + '-server')"></i></div></div>
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Public key</div><div class="col-8"><code class="text-break">{{ this.opnsenseData.serverPublicKey }}</code> <i class="bi bi-clipboard ms-2" role="button" @click="this.copyToClipboard(this.opnsenseData.serverPublicKey)"></i></div></div>
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Pre-shared key</div><div class="col-8"><small class="text-muted">(leave empty)</small></div></div>
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Allowed IPs</div><div class="col-8"><code>{{ this.opnsenseData.tunnelNetwork }}</code> <i class="bi bi-clipboard ms-2" role="button" @click="this.copyToClipboard(this.opnsenseData.tunnelNetwork)"></i></div></div>
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Endpoint address</div><div class="col-8"><code>{{ this.opnsenseData.serverEndpoint }}</code> <i class="bi bi-clipboard ms-2" role="button" @click="this.copyToClipboard(this.opnsenseData.serverEndpoint)"></i></div></div>
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Endpoint port</div><div class="col-8"><code>{{ this.opnsenseData.serverPort }}</code> <i class="bi bi-clipboard ms-2" role="button" @click="this.copyToClipboard(String(this.opnsenseData.serverPort))"></i></div></div>
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Instances</div><div class="col-8"><small class="text-muted">(auto-assigned in step 2)</small></div></div>
									<div class="row g-2"><div class="col-4 text-muted">Keepalive interval</div><div class="col-8"><code>{{ this.opnsenseData.keepalive }}</code> <i class="bi bi-clipboard ms-2" role="button" @click="this.copyToClipboard(String(this.opnsenseData.keepalive))"></i></div></div>
								</div>
								<div class="d-flex align-items-center mb-2 gap-2">
									<span class="badge bg-primary rounded-circle">2</span>
									<h6 class="mb-0" style="font-size: 0.9rem;">VPN → WireGuard → Instances → <strong>Add instance</strong></h6>
								</div>
								<div class="bg-body-tertiary p-3 rounded-3 border" style="font-size: 0.8rem;">
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Enabled</div><div class="col-8"><i class="bi bi-check-square"></i></div></div>
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Name</div><div class="col-8"><code>{{ this.opnsenseData.name }}</code> <i class="bi bi-clipboard ms-2" role="button" @click="this.copyToClipboard(this.opnsenseData.name)"></i></div></div>
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Public key</div><div class="col-8"><code class="text-break">{{ this.opnsenseData.publicKey }}</code> <i class="bi bi-clipboard ms-2" role="button" @click="this.copyToClipboard(this.opnsenseData.publicKey)"></i></div></div>
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Private key</div><div class="col-8"><code class="text-break">{{ this.opnsenseData.privateKey }}</code> <i class="bi bi-clipboard ms-2" role="button" @click="this.copyToClipboard(this.opnsenseData.privateKey)"></i></div></div>
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Listen port</div><div class="col-8"><code>51820</code> <i class="bi bi-clipboard ms-2" role="button" @click="this.copyToClipboard('51820')"></i></div></div>
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Tunnel address</div><div class="col-8"><code>{{ this.opnsenseData.clientTunnelAddress }}</code> <i class="bi bi-clipboard ms-2" role="button" @click="this.copyToClipboard(this.opnsenseData.clientTunnelAddress)"></i></div></div>
									<div class="row g-2 mb-2"><div class="col-4 text-muted">Peers</div><div class="col-8"><code>{{ this.opnsenseData.name }}-server</code> <small class="text-muted ms-2">(select from dropdown)</small></div></div>
									<div class="row g-2"><div class="col-4 text-muted">Disable routes</div><div class="col-8"><i class="bi bi-check-square"></i></div></div>
								</div>
							</div>
							<hr>
							<div class="d-flex gap-2 align-items-center">
								<strong>
									<LocaleText t="Reset Data Usage"></LocaleText>
								</strong>
								<div class="d-flex gap-2 ms-auto">
									<button class="btn bg-primary-subtle text-primary-emphasis rounded-3 flex-grow-1 shadow-sm"
										@click="this.resetPeerData('total')"
									>
										<i class="bi bi-arrow-down-up me-2"></i>
										<LocaleText t="Total"></LocaleText>
									</button>
									<button class="btn bg-primary-subtle text-primary-emphasis rounded-3 flex-grow-1 shadow-sm"
									        @click="this.resetPeerData('receive')"
									>
										<i class="bi bi-arrow-down me-2"></i>
										<LocaleText t="Received"></LocaleText>
									</button>
									<button class="btn bg-primary-subtle text-primary-emphasis rounded-3  flex-grow-1 shadow-sm"
									        @click="this.resetPeerData('sent')"
									>
										<i class="bi bi-arrow-up me-2"></i>
										<LocaleText t="Sent"></LocaleText>
									</button>
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>
			
		</div>

	</div>
</template>

<style scoped>
.toggleShowKey{
	position: absolute;
	top: 35px;
	right: 12px;
}
</style>