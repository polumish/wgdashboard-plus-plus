<script setup async>
import {computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch} from "vue";
import {useRoute} from "vue-router";
import {fetchGet, fetchPost} from "@/utilities/fetch.js";
import ProtocolBadge from "@/components/protocolBadge.vue";
import LocaleText from "@/components/text/localeText.vue";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {WireguardConfigurationsStore} from "@/stores/WireguardConfigurationsStore.js";
import PeerDataUsageCharts from "@/components/configurationComponents/peerListComponents/peerDataUsageCharts.vue";
import PeerSearch from "@/components/configurationComponents/peerSearch.vue";
import Peer from "@/components/configurationComponents/peer.vue";
import PeerListModals from "@/components/configurationComponents/peerListComponents/peerListModals.vue";
import PeerIntersectionObserver from "@/components/configurationComponents/peerIntersectionObserver.vue";
import ConfigurationDescription from "@/components/configurationComponents/configurationDescription.vue";
import PeerDetailsModal from "@/components/configurationComponents/peerDetailsModal.vue";
import {parseCidr} from "cidr-tools";

// Async Components
const PeerSearchBar = defineAsyncComponent(() => import("@/components/configurationComponents/peerSearchBar.vue"))
const PeerJobsAllModal = defineAsyncComponent(() => import("@/components/configurationComponents/peerJobsAllModal.vue"))
const PeerJobsLogsModal = defineAsyncComponent(() => import("@/components/configurationComponents/peerJobsLogsModal.vue"))
const EditConfigurationModal = defineAsyncComponent(() => import("@/components/configurationComponents/editConfiguration.vue"))
const SelectPeersModal = defineAsyncComponent(() => import("@/components/configurationComponents/selectPeers.vue"))
const PeerAddModal = defineAsyncComponent(() => import("@/components/configurationComponents/peerAddModal.vue"))
const OPNsenseGatewayModal = defineAsyncComponent(() => import("@/components/configurationComponents/opnsenseGatewayModal.vue"))

const dashboardStore = DashboardConfigurationStore()
const wireguardConfigurationStore = WireguardConfigurationsStore()
const route = useRoute()
const configurationInfo = ref({})
const configurationPeers = ref([])
const configurationToggling = ref(false)
const configurationModalSelectedPeer = ref({})
const tableSortBy = ref('name')
const tableSortAsc = ref(true)
const configurationModals = ref({
	peerNew: {
		modalOpen: false
	},
	opnsenseGateway: {
		modalOpen: false
	},
	peerSetting: {
		modalOpen: false,
	},
	peerScheduleJobs:{
		modalOpen: false,
	},
	peerQRCode: {
		modalOpen: false,
	},
	peerConfigurationFile: {
		modalOpen: false,
	},
	peerCreate: {
		modalOpen: false
	},
	peerScheduleJobsAll: {
		modalOpen: false
	},
	peerScheduleJobsLogs: {
		modalOpen: false
	},
	peerShare:{
		modalOpen: false,
	},
	editConfiguration: {
		modalOpen: false
	},
	selectPeers: {
		modalOpen: false
	},
	backupRestore: {
		modalOpen: false
	},
	deleteConfiguration: {
		modalOpen: false
	},
	editRawConfigurationFile: {
		modalOpen: false
	},
	assignPeer: {
		modalOpen: false
	},
	peerDetails: {
		modalOpen: false
	}
})
const peerSearchBar = ref(false)
// Fetch Peer =====================================
const fetchPeerList = async () => {
	await fetchGet("/api/getWireguardConfigurationInfo", {
		configurationName: route.params.id
	}, (res) => {
		if (res.status){
			configurationInfo.value = res.data.configurationInfo;
			configurationPeers.value = res.data.configurationPeers;
			
			configurationPeers.value.forEach(p => {
				p.restricted = false
			})
			res.data.configurationRestrictedPeers.forEach(x => {
				x.restricted = true;
				configurationPeers.value.push(x)
			})
		}
	})
}
await fetchPeerList()

// Fetch Peer Interval =====================================
const fetchPeerListInterval = ref(undefined)
const setFetchPeerListInterval = () => {
	clearInterval(fetchPeerListInterval.value)
	fetchPeerListInterval.value = setInterval(async () => {
		await fetchPeerList()
	},  parseInt(dashboardStore.Configuration.Server.dashboard_refresh_interval))
}
setFetchPeerListInterval()
onBeforeUnmount(() => {
	clearInterval(fetchPeerListInterval.value);
	fetchPeerListInterval.value = undefined;
	wireguardConfigurationStore.Filter.HiddenTags = []
})

watch(() => {
	return dashboardStore.Configuration.Server.dashboard_refresh_interval
}, () => {
	setFetchPeerListInterval()
})

// Toggle Configuration Method =====================================
const toggleConfiguration = async () => {
	configurationToggling.value = true;
	await fetchGet("/api/toggleWireguardConfiguration", {
		configurationName: configurationInfo.value.Name
	}, (res) => {
		if (res.status){
			dashboardStore.newMessage("Server", 
				`${configurationInfo.value.Name} ${res.data ? 'is on':'is off'}`, "success")
		}else{
			dashboardStore.newMessage("Server", res.message, 'danger')
		}
		wireguardConfigurationStore.Configurations
			.find(x => x.Name === configurationInfo.value.Name).Status = res.data
		configurationInfo.value.Status = res.data
		configurationToggling.value = false;
	})
}

// Configuration Summary =====================================
const configurationSummary = computed(() => {
	return {
		connectedPeers: configurationPeers.value.filter(x => x.status === "running").length,
		totalUsage: configurationPeers.value.length > 0 ?
			configurationPeers.value.filter(x => !x.restricted)
				.map(x => x.total_data + x.cumu_data).reduce((a, b) => a + b, 0).toFixed(4) : 0,
		totalReceive: configurationPeers.value.length > 0 ?
			configurationPeers.value.filter(x => !x.restricted)
				.map(x => x.total_receive + x.cumu_receive).reduce((a, b) => a + b, 0).toFixed(4) : 0,
		totalSent: configurationPeers.value.length > 0 ?
			configurationPeers.value.filter(x => !x.restricted)
				.map(x => x.total_sent + x.cumu_sent).reduce((a, b) => a + b, 0).toFixed(4) : 0
	}
})

const showPeersCount = ref(10)
const showPeersThreshold = 20;
const hiddenPeers = computed(() => {
	return wireguardConfigurationStore.Filter.HiddenTags.map(tag => {
		return configurationInfo.value.Info.PeerGroups[tag].Peers
	}).flat()
})
const taggedPeers = computed(() => {
	return Object.values(configurationInfo.value.Info.PeerGroups).map(x => x.Peers).flat()
})

const firstAllowedIPCount = (allowed_ip) => {
	try{
		return parseCidr(allowed_ip.replace(" ", "").split(",")[0]).start
	}catch (e){
		return 0
	}
}

const searchPeers = computed(() => {
	const result = wireguardConfigurationStore.searchString ?
		configurationPeers.value.filter(x => {
			return (x.name.includes(wireguardConfigurationStore.searchString) ||
				x.id.includes(wireguardConfigurationStore.searchString) ||
				x.allowed_ip.includes(wireguardConfigurationStore.searchString))
				&& !hiddenPeers.value.includes(x.id)
				&& (
					wireguardConfigurationStore.Filter.ShowAllPeersWhenHiddenTags || (!wireguardConfigurationStore.Filter.ShowAllPeersWhenHiddenTags && taggedPeers.value.includes(x.id))
				)
		}) : configurationPeers.value.filter(x => !hiddenPeers.value.includes(x.id) && (
			wireguardConfigurationStore.Filter.ShowAllPeersWhenHiddenTags || (!wireguardConfigurationStore.Filter.ShowAllPeersWhenHiddenTags && taggedPeers.value.includes(x.id))
		));

	if (dashboardStore.Configuration.Server.dashboard_sort === "restricted"){
		return result.sort((a, b) => {
			if ( a[dashboardStore.Configuration.Server.dashboard_sort]
				< b[dashboardStore.Configuration.Server.dashboard_sort] ){
				return 1;
			}
			if ( a[dashboardStore.Configuration.Server.dashboard_sort]
				> b[dashboardStore.Configuration.Server.dashboard_sort]){
				return -1;
			}
			return 0;
		}).slice(0, showPeersCount.value);
	}

	let re = []

	if (dashboardStore.Configuration.Server.dashboard_sort === 'allowed_ip'){
		re = result.sort((a, b) => {
			if ( firstAllowedIPCount(a[dashboardStore.Configuration.Server.dashboard_sort])
				< firstAllowedIPCount(b[dashboardStore.Configuration.Server.dashboard_sort]) ){
				return -1;
			}
			if ( firstAllowedIPCount(a[dashboardStore.Configuration.Server.dashboard_sort])
				> firstAllowedIPCount(b[dashboardStore.Configuration.Server.dashboard_sort])){
				return 1;
			}
			return 0;
		}).slice(0, showPeersCount.value)
	}else{
		re = result.sort((a, b) => {
			if ( a[dashboardStore.Configuration.Server.dashboard_sort]
				< b[dashboardStore.Configuration.Server.dashboard_sort] ){
				return -1;
			}
			if ( a[dashboardStore.Configuration.Server.dashboard_sort]
				> b[dashboardStore.Configuration.Server.dashboard_sort]){
				return 1;
			}
			return 0;
		}).slice(0, showPeersCount.value)
	}


	return re
})

const tableSortedPeers = computed(() => {
	const peers = [...searchPeers.value]
	const key = tableSortBy.value
	const asc = tableSortAsc.value
	return peers.sort((a, b) => {
		let va, vb
		if (key === 'total_data') {
			va = (a.cumu_receive + a.total_receive + a.cumu_sent + a.total_sent)
			vb = (b.cumu_receive + b.total_receive + b.cumu_sent + b.total_sent)
		} else if (key === 'latest_handshake') {
			va = a.latest_handshake === 'No Handshake' ? '' : a.latest_handshake
			vb = b.latest_handshake === 'No Handshake' ? '' : b.latest_handshake
		} else {
			va = a[key] || ''
			vb = b[key] || ''
		}
		if (va < vb) return asc ? -1 : 1
		if (va > vb) return asc ? 1 : -1
		return 0
	})
})

const tableDownloadPeer = (peer) => {
	fetchGet("/api/downloadPeer/" + route.params.id, { id: peer.id }, (res) => {
		if (res.status) {
			const blob = new Blob([res.data.file], { type: "text/conf" })
			const url = URL.createObjectURL(blob)
			const a = document.createElement("a")
			a.href = url
			a.download = `${res.data.fileName}.conf`
			a.click()
			dashboardStore.newMessage("WGDashboard", "Peer download started", "success")
		} else {
			dashboardStore.newMessage("Server", res.message, "danger")
		}
	})
}

const tableDeletePeer = (peer) => {
	if (!confirm("Are you sure to delete this peer?")) return
	fetchPost(`/api/deletePeers/${route.params.id}`, { peers: [peer.id] }, (res) => {
		dashboardStore.newMessage("Server", res.message, res.status ? "success" : "danger")
		fetchPeerList()
	})
}

const tableRestrictPeer = (peer) => {
	fetchPost(`/api/restrictPeers/${route.params.id}`, { peers: [peer.id] }, (res) => {
		dashboardStore.newMessage("Server", res.message, res.status ? "success" : "danger")
		fetchPeerList()
	})
}

const tableBroadcastAllowedIPs = (peer) => {
	if (!confirm(`Broadcast this peer's AllowedIPs (${peer.allowed_ip}) to all other peers?`)) return
	fetchPost(`/api/broadcastPeerAllowedIPs/${route.params.id}`, { id: peer.id }, (res) => {
		dashboardStore.newMessage("Server", res.message, res.status ? "success" : "danger")
		fetchPeerList()
	})
}

watch(() => route.query.id, (newValue) => {
	if (newValue){
		wireguardConfigurationStore.searchString = newValue
	}else{
		wireguardConfigurationStore.searchString = undefined
	}
}, {
	immediate: true
})
</script>

<template>
<div class="container-fluid" >
	<div class="d-flex align-items-sm-start flex-column flex-sm-row gap-3">
		<div>
			<div class="text-muted d-flex align-items-center gap-2">
				<h5 class="mb-0">
					<ProtocolBadge :protocol="configurationInfo.Protocol"></ProtocolBadge>
				</h5>
			</div>
			<div class="d-flex align-items-center gap-3">
				<h1 class="mb-0 display-4"><samp>{{configurationInfo.Name}}</samp></h1>
			</div>
		</div>
		<div class="ms-sm-auto d-flex gap-2 flex-column">
			<div class="card rounded-3 bg-transparent ">
				<div class="card-body py-2 d-flex align-items-center">
					<small class="text-muted">
						<LocaleText t="Status"></LocaleText>
					</small>
					<div class="dot ms-2" :class="{active: configurationInfo.Status}"></div>
					<div class="form-check form-switch mb-0 ms-auto pe-0 me-0">
						<label class="form-check-label" style="cursor: pointer" :for="'switch' + configurationInfo.id">
							<LocaleText t="On" v-if="configurationInfo.Status && !configurationToggling"></LocaleText>
							<LocaleText t="Off" v-else-if="!configurationInfo.Status && !configurationToggling"></LocaleText>
							<span v-if="configurationToggling"
							      class="spinner-border spinner-border-sm ms-2" aria-hidden="true">
							</span>
						</label>
						<input class="form-check-input"
						       style="cursor: pointer"
						       :disabled="configurationToggling"
						       type="checkbox" role="switch" :id="'switch' + configurationInfo.id"
						       @change="toggleConfiguration()"
						       v-model="configurationInfo.Status">
					</div>
				</div>
			</div>
			<div class="d-flex gap-2">
				<a
					role="button"
					@click="configurationModals.peerNew.modalOpen = true"
					class="titleBtn py-2 text-decoration-none btn text-primary-emphasis bg-primary-subtle rounded-3 border-1 border-primary-subtle ">
					<i class="bi bi-plus-circle me-2"></i>
					<LocaleText t="Peer"></LocaleText>
				</a>
				<a
					role="button"
					@click="configurationModals.opnsenseGateway.modalOpen = true"
					class="titleBtn py-2 text-decoration-none btn text-success-emphasis bg-success-subtle rounded-3 border-1 border-success-subtle ">
					<i class="bi bi-router me-2"></i>
					<LocaleText t="OPNsense"></LocaleText>
				</a>
				<button class="titleBtn py-2 text-decoration-none btn text-primary-emphasis bg-primary-subtle rounded-3 border-1 border-primary-subtle "
				        @click="configurationModals.editConfiguration.modalOpen = true"
				        type="button" aria-expanded="false">
					<i class="bi bi-gear-fill me-2"></i>
					<LocaleText t="Configuration Settings"></LocaleText>
				</button>
			</div>
		</div>
	</div>
	<hr>
	<ConfigurationDescription :configuration="configurationInfo"></ConfigurationDescription>
	<div class="row mt-3 gy-2 gx-2 mb-2">
		<div class="col-12 col-lg-3">
			<div class="card rounded-3 bg-transparent  h-100">
				<div class="card-body py-2 d-flex flex-column justify-content-center">
					<p class="mb-0 text-muted"><small>
						<LocaleText t="Address"></LocaleText>
					</small></p>
					{{configurationInfo.Address}}
				</div>
			</div>
		</div>
		<div class="col-12 col-lg-3">
			<div class="card rounded-3 bg-transparent h-100">
				<div class="card-body py-2 d-flex flex-column justify-content-center">
					<p class="mb-0 text-muted"><small>
						<LocaleText t="Listen Port"></LocaleText>
					</small></p>
					{{configurationInfo.ListenPort}}
				</div>
			</div>
		</div>
		<div style="word-break: break-all" class="col-12 col-lg-6">
			<div class="card rounded-3 bg-transparent h-100">
				<div class="card-body py-2 d-flex flex-column justify-content-center">
					<p class="mb-0 text-muted"><small>
						<LocaleText t="Public Key"></LocaleText>
					</small></p>
					<samp>{{configurationInfo.PublicKey}}</samp>
				</div>
			</div>
		</div>
	</div>
	<div class="row gx-2 gy-2 mb-2">
		<div class="col-12 col-lg-3">
			<div class="card rounded-3 bg-transparent  h-100">
				<div class="card-body d-flex">
					<div>
						<p class="mb-0 text-muted"><small>
							<LocaleText t="Connected Peers"></LocaleText>
						</small></p>
						<strong class="h4">
							{{configurationSummary.connectedPeers}} / {{configurationPeers.length}}
						</strong>
					</div>
					<i class="bi bi-ethernet ms-auto h2 text-muted"></i>
				</div>
			</div>
		</div>
		<div class="col-12 col-lg-3">
			<div class="card rounded-3 bg-transparent  h-100">
				<div class="card-body d-flex">
					<div>
						<p class="mb-0 text-muted"><small>
							<LocaleText t="Total Usage"></LocaleText>
						</small></p>
						<strong class="h4">{{configurationSummary.totalUsage}} GB</strong>
					</div>
					<i class="bi bi-arrow-down-up ms-auto h2 text-muted"></i>
				</div>
			</div>
		</div>
		<div class="col-12 col-lg-3">
			<div class="card rounded-3 bg-transparent  h-100">
				<div class="card-body d-flex">
					<div>
						<p class="mb-0 text-muted"><small>
							<LocaleText t="Total Received"></LocaleText>
						</small></p>
						<strong class="h4 text-primary">{{configurationSummary.totalReceive}} GB</strong>
					</div>
					<i class="bi bi-arrow-down ms-auto h2 text-muted"></i>
				</div>
			</div>
		</div>
		<div class="col-12 col-lg-3">
			<div class="card rounded-3 bg-transparent  h-100">
				<div class="card-body d-flex">
					<div>
						<p class="mb-0 text-muted"><small>
							<LocaleText t="Total Sent"></LocaleText>
						</small></p>
						<strong class="h4 text-success">{{configurationSummary.totalSent}} GB</strong>
					</div>
					<i class="bi bi-arrow-up ms-auto h2 text-muted"></i>
				</div>
			</div>
		</div>
	</div>
	<PeerDataUsageCharts
		:configurationPeers="configurationPeers"
		:configurationInfo="configurationInfo"
	></PeerDataUsageCharts>
	<hr>
	<div style="margin-bottom: 10rem">
		<PeerSearch
			v-if="configurationPeers.length > 0"
			@search="peerSearchBar = !peerSearchBar"
			@jobsAll="configurationModals.peerScheduleJobsAll.modalOpen = true"
			@jobLogs="configurationModals.peerScheduleJobsLogs.modalOpen = true"
			@editConfiguration="configurationModals.editConfiguration.modalOpen = true"
			@selectPeers="configurationModals.selectPeers.modalOpen = true"
			@backupRestore="configurationModals.backupRestore.modalOpen = true"
			@deleteConfiguration="configurationModals.deleteConfiguration.modalOpen = true"
			:configuration="configurationInfo">
		</PeerSearch>
		<!-- Table View -->
		<div v-if="dashboardStore.Configuration.Server.dashboard_peer_list_display === 'table'" class="table-responsive">
			<table class="table table-hover align-middle mb-0">
				<thead class="table-light">
					<tr>
						<th style="width: 30px"></th>
						<th role="button" @click="tableSortBy = 'name'; tableSortAsc = tableSortBy === 'name' ? !tableSortAsc : true">
							<small class="d-flex align-items-center gap-1">
								<LocaleText t="Name"></LocaleText>
								<i class="bi" :class="tableSortBy === 'name' ? (tableSortAsc ? 'bi-sort-up' : 'bi-sort-down') : 'bi-sort-up text-muted opacity-25'" style="font-size: 0.7rem"></i>
							</small>
						</th>
						<th>
							<small><LocaleText t="Allowed IPs"></LocaleText></small>
						</th>
						<th role="button" @click="tableSortBy = 'total_data'; tableSortAsc = tableSortBy === 'total_data' ? !tableSortAsc : false">
							<small class="d-flex align-items-center gap-1">
								<LocaleText t="Traffic"></LocaleText>
								<i class="bi" :class="tableSortBy === 'total_data' ? (tableSortAsc ? 'bi-sort-up' : 'bi-sort-down') : 'bi-sort-up text-muted opacity-25'" style="font-size: 0.7rem"></i>
							</small>
						</th>
						<th role="button" @click="tableSortBy = 'latest_handshake'; tableSortAsc = tableSortBy === 'latest_handshake' ? !tableSortAsc : false">
							<small class="d-flex align-items-center gap-1">
								<LocaleText t="Handshake"></LocaleText>
								<i class="bi" :class="tableSortBy === 'latest_handshake' ? (tableSortAsc ? 'bi-sort-up' : 'bi-sort-down') : 'bi-sort-up text-muted opacity-25'" style="font-size: 0.7rem"></i>
							</small>
						</th>
						<th><small><LocaleText t="Endpoint"></LocaleText></small></th>
						<th style="width: 40px"></th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="peer in tableSortedPeers" :key="peer.id"
						:class="{'table-warning': peer.restricted}"
						role="button"
						@click="configurationModals.peerSetting.modalOpen = true; configurationModalSelectedPeer = peer">
						<td>
							<span class="d-inline-block rounded-circle"
								  :style="{width: '10px', height: '10px', backgroundColor: peer.status === 'running' ? '#28a745' : '#6c757d', boxShadow: peer.status === 'running' ? '0 0 0 3px #28a74545' : 'none'}">
							</span>
						</td>
						<td>
							<strong class="d-block" style="font-size: 0.85rem">{{ peer.name || 'Untitled' }}</strong>
							<samp class="text-muted" style="font-size: 0.65rem">{{ peer.id.substring(0, 20) }}...</samp>
						</td>
						<td><small><samp>{{ peer.allowed_ip }}</samp></small></td>
						<td>
							<small class="d-flex flex-column">
								<span><i class="bi bi-arrow-down text-success me-1"></i>{{ (peer.cumu_receive + peer.total_receive).toFixed(2) }} GB</span>
								<span><i class="bi bi-arrow-up text-primary me-1"></i>{{ (peer.cumu_sent + peer.total_sent).toFixed(2) }} GB</span>
							</small>
						</td>
						<td><small class="text-muted">{{ peer.latest_handshake }}</small></td>
						<td><small class="text-muted"><samp>{{ peer.endpoint }}</samp></small></td>
						<td @click.stop class="position-relative">
							<div class="dropdown">
								<button class="btn btn-sm btn-body rounded-3" data-bs-toggle="dropdown">
									<i class="bi bi-three-dots-vertical"></i>
								</button>
								<ul class="dropdown-menu dropdown-menu-end rounded-3 shadow" style="min-width: 200px">
									<template v-if="peer.private_key">
										<li class="d-flex px-2 gap-1">
											<button class="btn btn-sm btn-body rounded-3 flex-fill" title="Download" @click="tableDownloadPeer(peer)"><i class="bi bi-download"></i></button>
											<button class="btn btn-sm btn-body rounded-3 flex-fill" title="QR Code" @click="configurationModalSelectedPeer = peer; configurationModals.peerQRCode.modalOpen = true"><i class="bi bi-qr-code"></i></button>
											<button class="btn btn-sm btn-body rounded-3 flex-fill" title="Config File" @click="configurationModalSelectedPeer = peer; configurationModals.peerConfigurationFile.modalOpen = true"><i class="bi bi-body-text"></i></button>
											<button class="btn btn-sm btn-body rounded-3 flex-fill" title="Share" @click="configurationModals.peerShare.modalOpen = true; configurationModalSelectedPeer = peer"><i class="bi bi-share"></i></button>
										</li>
										<li><hr class="dropdown-divider"></li>
									</template>
									<template v-else>
										<li><small class="dropdown-item text-muted" style="white-space: break-spaces; font-size: 0.7rem"><LocaleText t="Download & QR Code is not available due to no private key set for this peer"></LocaleText></small></li>
									</template>
									<li><a class="dropdown-item d-flex" role="button" @click="configurationModals.peerSetting.modalOpen = true; configurationModalSelectedPeer = peer"><i class="me-auto bi bi-pen"></i> <LocaleText t="Peer Settings"></LocaleText></a></li>
									<li><a class="dropdown-item d-flex" role="button" @click="configurationModals.peerScheduleJobs.modalOpen = true; configurationModalSelectedPeer = peer"><i class="me-auto bi bi-app-indicator"></i> <LocaleText t="Schedule Jobs"></LocaleText></a></li>
									<li><a class="dropdown-item d-flex" role="button" @click="configurationModalSelectedPeer = peer; configurationModals.assignPeer.modalOpen = true"><i class="me-auto bi bi-diagram-2"></i> <LocaleText t="Assign Peer"></LocaleText></a></li>
									<li><a class="dropdown-item d-flex" role="button" @click="tableBroadcastAllowedIPs(peer)"><i class="me-auto bi bi-broadcast"></i> <LocaleText t="Broadcast AllowedIPs"></LocaleText></a></li>
									<li><hr class="dropdown-divider"></li>
									<li><a class="dropdown-item d-flex text-warning" role="button" @click="tableRestrictPeer(peer)"><i class="me-auto bi bi-lock"></i> <LocaleText t="Restrict Access"></LocaleText></a></li>
									<li><a class="dropdown-item d-flex text-danger fw-bold" role="button" @click="tableDeletePeer(peer)"><i class="me-auto bi bi-trash"></i> <LocaleText t="Delete"></LocaleText></a></li>
								</ul>
							</div>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
		<!-- Card/List View -->
		<TransitionGroup v-else name="peerList" tag="div" class="row gx-2 gy-2 z-0 position-relative">
			<div class="col-12"
			     :class="{'col-lg-6 col-xl-4': dashboardStore.Configuration.Server.dashboard_peer_list_display === 'grid'}"
			     :key="peer.id"
			     v-for="(peer, order) in searchPeers">
				<Peer :Peer="peer"
					  :searchPeersLength="searchPeers.length"
					  :order="order"
					  :ConfigurationInfo="configurationInfo"
					  @details="configurationModals.peerDetails.modalOpen = true; configurationModalSelectedPeer = peer"
				      @share="configurationModals.peerShare.modalOpen = true; configurationModalSelectedPeer = peer"
				      @refresh="fetchPeerList()"

				      @jobs="configurationModals.peerScheduleJobs.modalOpen = true; configurationModalSelectedPeer = peer"
				      @setting="configurationModals.peerSetting.modalOpen = true; configurationModalSelectedPeer = peer"
				      @qrcode="configurationModalSelectedPeer = peer; configurationModals.peerQRCode.modalOpen = true;"
				      @configurationFile="configurationModalSelectedPeer = peer; configurationModals.peerConfigurationFile.modalOpen = true;"
				      @assign="configurationModalSelectedPeer = peer; configurationModals.assignPeer.modalOpen = true;"
				></Peer>
			</div>
		</TransitionGroup>
		
	</div>
	<Transition name="slide-fade">
		<PeerSearchBar
			v-if="peerSearchBar"
			:ConfigurationInfo="configurationInfo"
			@close="peerSearchBar = false"></PeerSearchBar>
	</Transition>
	<PeerListModals 
		:configurationModals="configurationModals"
		:configurationModalSelectedPeer="configurationModalSelectedPeer"
		@refresh="fetchPeerList()"
	></PeerListModals>
	<TransitionGroup name="zoom">
		<Suspense key="PeerAddModal">
			<PeerAddModal
				v-if="configurationModals.peerNew.modalOpen"
				@close="configurationModals.peerNew.modalOpen = false"
				@addedPeers="configurationModals.peerNew.modalOpen = false; fetchPeerList()"
			></PeerAddModal>
		</Suspense>
		<OPNsenseGatewayModal
			key="OPNsenseGatewayModal"
			v-if="configurationModals.opnsenseGateway.modalOpen"
			@close="configurationModals.opnsenseGateway.modalOpen = false"
			@added="fetchPeerList()"
		></OPNsenseGatewayModal>
		<PeerJobsAllModal
			key="PeerJobsAllModal"
			v-if="configurationModals.peerScheduleJobsAll.modalOpen"
			@refresh="fetchPeerList()"
			@allLogs="configurationModals.peerScheduleJobsLogs.modalOpen = true"
			@close="configurationModals.peerScheduleJobsAll.modalOpen = false"
			:configurationPeers="configurationPeers"
		>
		</PeerJobsAllModal>
		<PeerJobsLogsModal
			key="PeerJobsLogsModal"
			v-if="configurationModals.peerScheduleJobsLogs.modalOpen" 
			@close="configurationModals.peerScheduleJobsLogs.modalOpen = false"
			:configurationInfo="configurationInfo">
		</PeerJobsLogsModal>
		<EditConfigurationModal
			key="EditConfigurationModal"
			@editRaw="configurationModals.editRawConfigurationFile.modalOpen = true"
			@close="configurationModals.editConfiguration.modalOpen = false"
			@dataChanged="(d) => configurationInfo = d"
			@refresh="fetchPeerList()"
			@backupRestore="configurationModals.backupRestore.modalOpen = true"
			@deleteConfiguration="configurationModals.deleteConfiguration.modalOpen = true"
			:configurationInfo="configurationInfo"
			v-if="configurationModals.editConfiguration.modalOpen">
		</EditConfigurationModal>
		<SelectPeersModal
			@refresh="fetchPeerList()"
			v-if="configurationModals.selectPeers.modalOpen"
			:configurationPeers="configurationPeers"
			@close="configurationModals.selectPeers.modalOpen = false"
		></SelectPeersModal>
		<PeerDetailsModal
			key="PeerDetailsModal"
			v-if="configurationModals.peerDetails.modalOpen"
			:selectedPeer="searchPeers.find(x => x.id === configurationModalSelectedPeer.id)"
			@close="configurationModals.peerDetails.modalOpen = false"
		>
		</PeerDetailsModal>
	</TransitionGroup>
	<PeerIntersectionObserver
		:showPeersCount="showPeersCount"
		:peerListLength="searchPeers.length"
		@loadMore="showPeersCount += showPeersThreshold"></PeerIntersectionObserver>
</div>
</template>

<style scoped>
.peerNav .nav-link{
	&.active{
		background-color: #efefef;
	}
}

th, td{
	background-color: transparent !important;
}

@media screen and (max-width: 576px) {
	.titleBtn{
		flex-basis: 100%;
	}
}
</style>