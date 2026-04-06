<script setup async>
import {computed, onMounted, ref, watch} from "vue";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {fetchGet, fetchPost} from "@/utilities/fetch.js";
import {useRoute} from "vue-router";
import LocaleText from "@/components/text/localeText.vue";
import EndpointAllowedIps from "@/components/configurationComponents/newPeersComponents/endpointAllowedIps.vue";
import AllowedIPsInput from "@/components/configurationComponents/newPeersComponents/allowedIPsInput.vue";
import DnsInput from "@/components/configurationComponents/newPeersComponents/dnsInput.vue";
import NameInput from "@/components/configurationComponents/newPeersComponents/nameInput.vue";
import PrivatePublicKeyInput from "@/components/configurationComponents/newPeersComponents/privatePublicKeyInput.vue";
import BulkAdd from "@/components/configurationComponents/newPeersComponents/bulkAdd.vue";
import PresharedKeyInput from "@/components/configurationComponents/newPeersComponents/presharedKeyInput.vue";
import MtuInput from "@/components/configurationComponents/newPeersComponents/mtuInput.vue";
import PersistentKeepAliveInput
	from "@/components/configurationComponents/newPeersComponents/persistentKeepAliveInput.vue";
import {WireguardConfigurationsStore} from "@/stores/WireguardConfigurationsStore.js";

const dashboardStore = DashboardConfigurationStore()
const wireguardStore = WireguardConfigurationsStore()
const _currentConfig = wireguardStore.Configurations.find(x => x.Name === useRoute().params.id)
const _configAddress = _currentConfig ? (_currentConfig.Address || '').split(',')[0].trim() : ''
const _defaultEAIP = _configAddress || dashboardStore.Configuration.Peers.peer_endpoint_allowed_ip
const peerData = ref({
	bulkAdd: false,
	bulkAddAmount: 0,
	name: "",
	allowed_ips: [],
	private_key: "",
	public_key: "",
	DNS: dashboardStore.Configuration.Peers.peer_global_dns,
	endpoint_allowed_ip: _defaultEAIP,
	keepalive: parseInt(dashboardStore.Configuration.Peers.peer_keep_alive),
	mtu: parseInt(dashboardStore.Configuration.Peers.peer_mtu),
	preshared_key: "",
	preshared_key_bulkAdd: false,
	advanced_security: "off",
	allowed_ips_validation: true,
	is_gateway: 0,
})
const availableIp = ref([])
const saving = ref(false)

const route = useRoute()
await fetchGet("/api/getAvailableIPs/" + route.params.id, {}, (res) => {
	if (res.status){
		availableIp.value = res.data;
	}
})

const emits = defineEmits(['close', 'addedPeers'])

const getProtocol = computed(() => {
	return wireguardStore.Configurations.find(x => x.Name === route.params.id).Protocol;
})

const allRequireFieldsFilled = computed(() => {
	let status = true;
	if (peerData.value.bulkAdd){
		if(peerData.value.bulkAddAmount.length === 0 || peerData.value.bulkAddAmount > availableIp.value.length){
			status = false;
		}
	}else{
		let requireFields =
			["allowed_ips", "private_key", "public_key", "endpoint_allowed_ip", "keepalive", "mtu"]
		requireFields.forEach(x => {
			if (peerData.value[x].length === 0) status = false;
		});
	}
	return status;
})

const peerCreate = () => {
	saving.value = true
	fetchPost("/api/addPeers/" + route.params.id, peerData.value, (res) => {
		if (res.status){
			dashboardStore.newMessage("Server", "Peer created successfully", "success")
			emits('addedPeers')
		}else{
			dashboardStore.newMessage("Server", res.message, "danger")
		}
		saving.value = false;
	})
}

watch(() => {
	return peerData.value.bulkAddAmount
}, () => {
	if (peerData.value.bulkAddAmount > availableIp.value.length){
		peerData.value.bulkAddAmount = availableIp.value.length
	}
})
</script>

<template>
	<div class="peerSettingContainer w-100 h-100 position-absolute top-0 start-0 overflow-y-scroll" ref="editConfigurationContainer">
		<div class="container d-flex h-100 w-100">
			<div class="m-auto modal-dialog-centered dashboardModal" style="width: 1000px">
				<div class="card rounded-3 shadow flex-grow-1">
					<div class="card-header bg-transparent d-flex align-items-center gap-2 border-0 p-4">
						<h4 class="mb-0">
							<LocaleText t="Add Peers"></LocaleText>
						</h4>
						<button type="button" class="btn-close ms-auto" @click="emits('close')"></button>
					</div>
					<div class="card-body px-4 pb-4">
						<div class="d-flex flex-column gap-2">
							<BulkAdd :saving="saving" :data="peerData" :availableIp="availableIp"></BulkAdd>
							<template v-if="!peerData.bulkAdd">
								<hr class="mb-0 mt-2">
								<div>
									<label class="form-label">
										<small class="text-muted"><LocaleText t="Device Type"></LocaleText></small>
									</label>
									<div class="d-flex gap-3">
										<div class="form-check">
											<input class="form-check-input" type="radio" id="peerTypeClient"
												:value="0" v-model="peerData.is_gateway" :disabled="saving">
											<label class="form-check-label" for="peerTypeClient">
												<small>Client</small>
											</label>
										</div>
										<div class="form-check">
											<input class="form-check-input" type="radio" id="peerTypeServer"
												:value="2" v-model="peerData.is_gateway" :disabled="saving">
											<label class="form-check-label" for="peerTypeServer">
												<i class="bi bi-hdd-rack me-1"></i><small>Server</small>
											</label>
										</div>
										<div class="form-check">
											<input class="form-check-input" type="radio" id="peerTypeGateway"
												:value="1" v-model="peerData.is_gateway" :disabled="saving">
											<label class="form-check-label" for="peerTypeGateway">
												<i class="bi bi-router me-1"></i><small>Gateway</small>
											</label>
										</div>
									</div>
								</div>
								<NameInput :saving="saving" :data="peerData"></NameInput>
								<PrivatePublicKeyInput :saving="saving" :data="peerData"></PrivatePublicKeyInput>
								<AllowedIPsInput :availableIp="availableIp" :saving="saving" :data="peerData"></AllowedIPsInput>
							</template>
						</div>
						<hr>
						<div class="accordion mb-3" id="peerAddModalAccordion">
							<div class="accordion-item">
								<h2 class="accordion-header">
									<button class="accordion-button collapsed rounded-3" type="button" 
									        data-bs-toggle="collapse" data-bs-target="#peerAddModalAccordionAdvancedOptions">
										<LocaleText t="Advanced Options"></LocaleText>
									</button>
								</h2>
								<div id="peerAddModalAccordionAdvancedOptions" 
								     class="accordion-collapse collapse collapsed" data-bs-parent="#peerAddModalAccordion">
									<div class="accordion-body rounded-bottom-3">
										<div class="d-flex flex-column gap-2">
											<DnsInput :saving="saving" :data="peerData"></DnsInput>
											<EndpointAllowedIps :saving="saving" :data="peerData"></EndpointAllowedIps>
											<div class="row gy-3">
												<div class="col-sm" v-if="!peerData.bulkAdd">
													<PresharedKeyInput :saving="saving" :data="peerData" :bulk="peerData.bulkAdd"></PresharedKeyInput>
												</div>

												<div class="col-sm">
													<MtuInput :saving="saving" :data="peerData"></MtuInput>
												</div>
												<div class="col-sm">
													<PersistentKeepAliveInput :saving="saving" :data="peerData"></PersistentKeepAliveInput>
												</div>
												<div class="col-12" v-if="peerData.bulkAdd">
													<div class="form-check form-switch">
														<input class="form-check-input" type="checkbox" role="switch"
														       v-model="peerData.preshared_key_bulkAdd"
														       id="bullAdd_PresharedKey_Switch" checked>
														<label class="form-check-label" for="bullAdd_PresharedKey_Switch">
															<small class="fw-bold">
																<LocaleText t="Pre-Shared Key"></LocaleText> <LocaleText t="Enabled" v-if="peerData.preshared_key_bulkAdd"></LocaleText><LocaleText t="Disabled" v-else></LocaleText>
															</small>
														</label>
													</div>
												</div>
											</div>
										</div>
										
									</div>
								</div>
							</div>
							
							
						</div>
						<div class="d-flex mt-2">
							<button class="ms-auto btn btn-dark btn-brand rounded-3 px-3 py-2 shadow"
							        :disabled="!allRequireFieldsFilled || saving"
							        @click="peerCreate()"
							>
								<i class="bi bi-plus-circle-fill me-2" v-if="!saving"></i>
								<LocaleText t="Adding..." v-if="saving"></LocaleText>
								<LocaleText t="Add" v-else></LocaleText>
							</button>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>

</style>