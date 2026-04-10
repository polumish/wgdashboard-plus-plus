<script setup async>
import {computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch} from "vue";
import {useRoute} from "vue-router";
import {fetchGet, fetchPost} from "@/utilities/fetch.js";
import ProtocolBadge from "@/components/protocolBadge.vue";
import LocaleText from "@/components/text/localeText.vue";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {WireguardConfigurationsStore} from "@/stores/WireguardConfigurationsStore.js";
import NetworkDiagnostics from "@/components/networkDiagnostics/NetworkDiagnostics.vue";
import PeerSearch from "@/components/configurationComponents/peerSearch.vue";
import Peer from "@/components/configurationComponents/peer.vue";
import PeerListModals from "@/components/configurationComponents/peerListComponents/peerListModals.vue";
import PeerIntersectionObserver from "@/components/configurationComponents/peerIntersectionObserver.vue";
import PeerDetailsModal from "@/components/configurationComponents/peerDetailsModal.vue";
import {parseCidr} from "cidr-tools";
import {formatTraffic} from "@/utilities/formatBytes.js";

// Async Components
const PeerSearchBar = defineAsyncComponent(() => import("@/components/configurationComponents/peerSearchBar.vue"))
const PeerJobsAllModal = defineAsyncComponent(() => import("@/components/configurationComponents/peerJobsAllModal.vue"))
const PeerJobsLogsModal = defineAsyncComponent(() => import("@/components/configurationComponents/peerJobsLogsModal.vue"))
const EditConfigurationModal = defineAsyncComponent(() => import("@/components/configurationComponents/editConfiguration.vue"))
const SelectPeersModal = defineAsyncComponent(() => import("@/components/configurationComponents/selectPeers.vue"))
const PeerAddModal = defineAsyncComponent(() => import("@/components/configurationComponents/peerAddModal.vue"))
const OPNsenseGatewayModal = defineAsyncComponent(() => import("@/components/configurationComponents/opnsenseGatewayModal.vue"))
const ConfigurationBackups = defineAsyncComponent(() => import("@/components/configurationComponents/configurationBackups.vue"))

const dashboardStore = DashboardConfigurationStore()
const wireguardConfigurationStore = WireguardConfigurationsStore()
const route = useRoute()
const configurationInfo = ref({})
const configurationPeers = ref([])
const policyRoutes = ref([])
const policyRouteModalOpen = ref(false)
const policyRoutePos = ref({x: 0, y: 0})
const policyRouteFiltered = ref([])
function openPolicyRouteModal(event, peer) {
	const rect = event.target.getBoundingClientRect()
	policyRoutePos.value = {x: rect.left, y: rect.top}
	const peerNets = (peer.allowed_ip || '').split(',').map(s => s.trim()).filter(Boolean)
	policyRouteFiltered.value = policyRoutes.value.filter(r =>
		peerNets.some(net => net === r.dest_subnet || r.dest_subnet.startsWith(net.split('/')[0]))
	)
	policyRouteModalOpen.value = true
}
const configurationToggling = ref(false)
const configurationModalSelectedPeer = ref({})
const tableSortBy = ref('status')
const tableSortAsc = ref(true)
const configInfoExpanded = ref(false)
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
	configurationBackups: {
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
	fetchGet("/api/policyRouting/status/" + route.params.id, {}, (res) => {
		if (res.status) {
			policyRoutes.value = res.data
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
	},  parseInt(dashboardStore.Configuration.Server.dashboard_refresh_interval, 10) || 10000)
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
	const activePeers = configurationPeers.value.filter(x => !x.restricted)
	const sum = (key1, key2) => activePeers.map(x => x[key1] + x[key2]).reduce((a, b) => a + b, 0)
	return {
		connectedPeers: configurationPeers.value.filter(x => x.status === "running").length,
		totalUsage: configurationPeers.value.length > 0 ? sum('total_data', 'cumu_data') : 0,
		totalReceive: configurationPeers.value.length > 0 ? sum('total_receive', 'cumu_receive') : 0,
		totalSent: configurationPeers.value.length > 0 ? sum('total_sent', 'cumu_sent') : 0
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


	// Sort by device type: gateways → servers → clients
	const gateways = re.filter(p => p.is_gateway === true || p.is_gateway === 1)
	const servers = re.filter(p => p.is_gateway === 2)
	const clients = re.filter(p => !p.is_gateway || p.is_gateway === 0)
	return [...gateways, ...servers, ...clients]
})

const _handshakeToTimestamp = (hs) => {
	if (!hs || hs === 'No Handshake' || hs === 'N/A') return 0
	const d = new Date(hs)
	return isNaN(d.getTime()) ? 0 : d.getTime()
}

const tableSortedPeers = computed(() => {
	const peers = [...searchPeers.value]
	const key = tableSortBy.value
	const asc = tableSortAsc.value
	return peers.sort((a, b) => {
		let va, vb
		if (key === 'status') {
			const aOnline = a.status === 'running' ? 1 : 0
			const bOnline = b.status === 'running' ? 1 : 0
			if (aOnline !== bOnline) return asc ? bOnline - aOnline : aOnline - bOnline
			const aTs = _handshakeToTimestamp(a.latest_handshake)
			const bTs = _handshakeToTimestamp(b.latest_handshake)
			return asc ? bTs - aTs : aTs - bTs
		} else if (key === 'total_data') {
			va = (a.cumu_receive + a.total_receive + a.cumu_sent + a.total_sent)
			vb = (b.cumu_receive + b.total_receive + b.cumu_sent + b.total_sent)
		} else if (key === 'latest_handshake') {
			va = _handshakeToTimestamp(a.latest_handshake)
			vb = _handshakeToTimestamp(b.latest_handshake)
		} else {
			va = a[key] || ''
			vb = b[key] || ''
		}
		if (va < vb) return asc ? -1 : 1
		if (va > vb) return asc ? 1 : -1
		return 0
	}).sort((a, b) => {
		const typeOrder = (p) => p.is_gateway === true || p.is_gateway === 1 ? 0 : p.is_gateway === 2 ? 1 : 2
		return typeOrder(a) - typeOrder(b)
	})
})

const columnsLeftPeers = computed(() => {
	const all = tableSortedPeers.value
	return all.slice(0, Math.ceil(all.length / 2))
})
const columnsRightPeers = computed(() => {
	const all = tableSortedPeers.value
	return all.slice(Math.ceil(all.length / 2))
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
	fetchPost(`/api/deletePeers/${route.params.id}`, { peers: [peer.id] }, async (res) => {
		dashboardStore.newMessage("Server", res.message, res.status ? "success" : "danger")
		if (res.status) {
			// Remove immediately from local state for instant UI feedback
			configurationPeers.value = configurationPeers.value.filter(p => p.id !== peer.id)
		}
		await fetchPeerList()
	})
}

const tableRestrictPeer = (peer) => {
	fetchPost(`/api/restrictPeers/${route.params.id}`, { peers: [peer.id] }, (res) => {
		dashboardStore.newMessage("Server", res.message, res.status ? "success" : "danger")
		fetchPeerList()
	})
}

const tableAllowAccessPeer = (peer) => {
	fetchPost(`/api/allowAccessPeers/${route.params.id}`, { peers: [peer.id] }, (res) => {
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
	<div class="d-flex align-items-sm-center flex-column flex-sm-row gap-1">
		<div class="d-flex align-items-center gap-2">
			<ProtocolBadge :protocol="configurationInfo.Protocol"></ProtocolBadge>
			<h4 class="mb-0"><samp>{{configurationInfo.Name}}</samp></h4>
		</div>
		<div class="ms-sm-auto d-flex gap-1 flex-column">
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
	<div class="card rounded-3 bg-transparent mt-3 mb-2">
		<div class="card-body py-2 px-3 d-flex align-items-center gap-3" role="button" @click="configInfoExpanded = !configInfoExpanded">
			<i class="bi" :class="configInfoExpanded ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
			<small class="d-flex align-items-center gap-2">
				<span class="badge text-bg-primary">
					{{configurationSummary.connectedPeers}} / {{configurationPeers.length}} peers
				</span>
			</small>
			<small class="text-muted"><samp>{{configurationInfo.Address}}</samp></small>
			<small class="text-muted">:<samp>{{configurationInfo.ListenPort}}</samp></small>
			<small class="text-muted ms-auto">
				<i class="bi bi-arrow-down-up me-1"></i>{{ formatTraffic(configurationSummary.totalUsage) }}
			</small>
		</div>
		<Transition name="fade2">
			<div v-if="configInfoExpanded" class="border-top">
				<NetworkDiagnostics mode="single" :interface="configurationInfo.Name" />
			</div>
		</Transition>
	</div>
	<div style="margin-bottom: 10rem">
		<PeerSearch
			v-if="configurationPeers.length > 0"
			@search="peerSearchBar = !peerSearchBar"
			@jobsAll="configurationModals.peerScheduleJobsAll.modalOpen = true"
			@jobLogs="configurationModals.peerScheduleJobsLogs.modalOpen = true"
			@editConfiguration="configurationModals.editConfiguration.modalOpen = true"
			@selectPeers="configurationModals.selectPeers.modalOpen = true"
			@backupRestore="configurationModals.backupRestore.modalOpen = true"
			@backups="configurationModals.configurationBackups.modalOpen = true"
			@deleteConfiguration="configurationModals.deleteConfiguration.modalOpen = true"
			:configuration="configurationInfo">
		</PeerSearch>
		<!-- Table View -->
		<div v-if="dashboardStore.Configuration.Server.dashboard_peer_list_display === 'table'" class="table-responsive">
			<table class="table table-striped table-hover align-middle mb-0 peer-table-fixed">
				<colgroup>
					<col style="width: 14%;">
					<col style="width: 24%;">
					<col style="width: 22%;">
					<col style="width: 14%;">
					<col style="width: 22%;">
					<col style="width: 4%;">
				</colgroup>
				<thead>
					<tr class="text-body-secondary">
						<th role="button" @click="tableSortBy = 'status'; tableSortAsc = tableSortBy === 'status' ? !tableSortAsc : true" title="Sort by status">
							<small class="d-flex align-items-center gap-1">
								<LocaleText t="Status"></LocaleText>
								<i class="bi" :class="tableSortBy === 'status' ? (tableSortAsc ? 'bi-sort-up' : 'bi-sort-down') : 'bi-sort-up text-muted opacity-25'" style="font-size: 0.7rem"></i>
							</small>
						</th>
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
							<th><small><LocaleText t="Endpoint"></LocaleText></small></th>
						<th></th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="peer in tableSortedPeers" :key="peer.id"
						:class="{'table-warning': peer.restricted, 'gateway-row': peer.is_gateway === true || peer.is_gateway === 1, 'server-row': peer.is_gateway === 2}"
						role="button"
						@click="configurationModals.peerSetting.modalOpen = true; configurationModalSelectedPeer = peer">
						<td>
							<div class="d-flex align-items-center gap-1">
								<span class="d-inline-block rounded-circle flex-shrink-0"
									  :style="{width: '10px', height: '10px', backgroundColor: peer.status === 'running' ? '#28a745' : '#6c757d', boxShadow: peer.status === 'running' ? '0 0 0 3px #28a74545' : 'none'}">
								</span>
								<small class="text-muted" style="font-size: 0.7rem; white-space: nowrap;"
									   v-if="peer.latest_handshake && peer.latest_handshake !== 'No Handshake'">
									{{ peer.latest_handshake }}
								</small>
							</div>
						</td>
						<td>
							<strong class="d-block" style="font-size: 0.85rem">
								<span v-if="peer.is_gateway === true || peer.is_gateway === 1" class="badge bg-info-subtle text-info-emphasis rounded-3 me-1" title="Gateway" style="font-size: 0.65rem;">
									<i class="bi bi-router"></i> GW
								</span>
								<span v-else-if="peer.is_gateway === 2" class="badge bg-success-subtle text-success-emphasis rounded-3 me-1" title="Server" style="font-size: 0.65rem;">
									<i class="bi bi-hdd-rack"></i> SRV
								</span>
								<template v-if="(peer.is_gateway === true || peer.is_gateway === 1) && policyRoutes.length > 0">
									<span class="badge rounded-3 me-1"
										:class="policyRoutes.some(r => r.active) ? 'bg-success-subtle text-success-emphasis' : 'bg-secondary-subtle text-secondary-emphasis'"
										style="font-size: 0.65rem; cursor: pointer;"
										@click.stop.prevent="openPolicyRouteModal($event, peer)">
										<i class="bi bi-diagram-3"></i> Route
									</span>
								</template>
								{{ peer.name || 'Untitled' }}
							</strong>
						</td>
						<td :title="peer.allowed_ip"><small><samp>{{ peer.allowed_ip }}</samp></small></td>
						<td>
							<small class="d-flex flex-column">
								<span><i class="bi bi-arrow-down text-success me-1"></i>{{ formatTraffic(peer.cumu_receive + peer.total_receive) }}</span>
								<span><i class="bi bi-arrow-up text-primary me-1"></i>{{ formatTraffic(peer.cumu_sent + peer.total_sent) }}</span>
							</small>
						</td>
						<td :title="peer.endpoint"><small class="text-muted"><samp>{{ peer.endpoint }}</samp></small></td>
						<td @click.stop>
							<div class="dropdown">
								<button class="btn btn-sm btn-body rounded-3" data-bs-toggle="dropdown" data-bs-display="static">
									<i class="bi bi-three-dots-vertical"></i>
								</button>
								<ul class="dropdown-menu dropdown-menu-end rounded-3 shadow" style="min-width: 200px;">
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
									<li v-if="!peer.restricted"><a class="dropdown-item d-flex text-warning" role="button" @click="tableRestrictPeer(peer)"><i class="me-auto bi bi-lock"></i> <LocaleText t="Restrict Access"></LocaleText></a></li>
									<li v-else><a class="dropdown-item d-flex text-success" role="button" @click="tableAllowAccessPeer(peer)"><i class="me-auto bi bi-unlock"></i> <LocaleText t="Allow Access"></LocaleText></a></li>
									<li><a class="dropdown-item d-flex text-danger fw-bold" role="button" @click="tableDeletePeer(peer)"><i class="me-auto bi bi-trash"></i> <LocaleText t="Delete"></LocaleText></a></li>
								</ul>
							</div>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
		<!-- Columns View (dual tables) -->
		<div v-else-if="dashboardStore.Configuration.Server.dashboard_peer_list_display === 'columns'" class="d-flex gap-2" style="align-items: flex-start;">
			<div class="flex-fill" style="min-width: 0;" v-for="(half, hi) in [columnsLeftPeers, columnsRightPeers]" :key="hi">
				<table class="table table-striped table-hover align-middle mb-0" style="font-size: 0.82rem;">
					<thead>
						<tr class="text-body-secondary">
							<th style="width: 14px"></th>
							<th><small><LocaleText t="Name"></LocaleText></small></th>
							<th><small><LocaleText t="Allowed IPs"></LocaleText></small></th>
							<th><small><LocaleText t="Traffic"></LocaleText></small></th>
							<th style="width: 30px"></th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="peer in half" :key="peer.id"
							:class="{'table-warning': peer.restricted, 'gateway-row': peer.is_gateway === true || peer.is_gateway === 1, 'server-row': peer.is_gateway === 2}"
							role="button"
							@click="configurationModals.peerSetting.modalOpen = true; configurationModalSelectedPeer = peer">
							<td style="padding: 0.25rem;">
								<span class="d-inline-block rounded-circle"
									  :style="{width: '8px', height: '8px', backgroundColor: peer.status === 'running' ? '#28a745' : '#6c757d'}">
								</span>
							</td>
							<td>
								<strong style="font-size: 0.82rem;">
									<span v-if="peer.is_gateway === true || peer.is_gateway === 1" class="badge bg-info-subtle text-info-emphasis rounded-3 me-1" title="Gateway" style="font-size: 0.62rem;">
										<i class="bi bi-router"></i> GW
									</span>
									<span v-else-if="peer.is_gateway === 2" class="badge bg-success-subtle text-success-emphasis rounded-3 me-1" title="Server" style="font-size: 0.62rem;">
										<i class="bi bi-hdd-rack"></i> SRV
									</span>
									<template v-if="(peer.is_gateway === true || peer.is_gateway === 1) && policyRoutes.length > 0">
										<span class="badge rounded-3 me-1"
											:class="policyRoutes.some(r => r.active) ? 'bg-success-subtle text-success-emphasis' : 'bg-secondary-subtle text-secondary-emphasis'"
											style="font-size: 0.62rem; cursor: pointer;"
											@click.stop.prevent="openPolicyRouteModal($event, peer)">
											<i class="bi bi-diagram-3"></i> Route
										</span>
									</template>
									{{ peer.name || 'Untitled' }}
								</strong>
							</td>
							<td><small><samp>{{ peer.allowed_ip }}</samp></small></td>
							<td>
								<small style="white-space: nowrap;">
									<i class="bi bi-arrow-down text-success"></i>{{ (peer.cumu_receive + peer.total_receive).toFixed(2) }}
									<i class="bi bi-arrow-up text-primary ms-1"></i>{{ (peer.cumu_sent + peer.total_sent).toFixed(2) }}
								</small>
							</td>
							<td @click.stop>
								<div class="dropdown">
									<button class="btn btn-sm btn-body rounded-3" data-bs-toggle="dropdown" data-bs-display="static">
										<i class="bi bi-three-dots-vertical"></i>
									</button>
									<ul class="dropdown-menu dropdown-menu-end rounded-3 shadow" style="min-width: 200px;">
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
										<li v-if="!peer.restricted"><a class="dropdown-item d-flex text-warning" role="button" @click="tableRestrictPeer(peer)"><i class="me-auto bi bi-lock"></i> <LocaleText t="Restrict Access"></LocaleText></a></li>
										<li v-else><a class="dropdown-item d-flex text-success" role="button" @click="tableAllowAccessPeer(peer)"><i class="me-auto bi bi-unlock"></i> <LocaleText t="Allow Access"></LocaleText></a></li>
										<li><a class="dropdown-item d-flex text-danger fw-bold" role="button" @click="tableDeletePeer(peer)"><i class="me-auto bi bi-trash"></i> <LocaleText t="Delete"></LocaleText></a></li>
									</ul>
								</div>
							</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>
		<!-- Card/List View -->
		<TransitionGroup v-else name="peerList" tag="div" class="row gx-2 gy-2 z-0 position-relative">
			<div class="col-12"
			     :class="{
			     	'col-lg-6 col-xl-4': dashboardStore.Configuration.Server.dashboard_peer_list_display === 'grid'
			     }"
			     :key="peer.id"
			     v-for="(peer, order) in searchPeers">
				<Peer :Peer="peer"
					  :searchPeersLength="searchPeers.length"
					  :order="order"
					  :ConfigurationInfo="configurationInfo"
					  :policyRoutes="policyRoutes"
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
		<ConfigurationBackups
			key="ConfigurationBackups"
			v-if="configurationModals.configurationBackups.modalOpen"
			@close="configurationModals.configurationBackups.modalOpen = false"
			@refreshPeersList="fetchPeerList()"
		></ConfigurationBackups>
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
	<Teleport to="body">
		<div v-if="policyRouteModalOpen" class="policy-route-overlay" @mousedown="policyRouteModalOpen = false">
			<div class="policy-route-modal shadow-lg rounded-3 p-3" @mousedown.stop
				:style="{left: policyRoutePos.x + 'px', bottom: 'calc(100vh - ' + policyRoutePos.y + 'px + 4px)'}"
			>
				<div class="d-flex align-items-center mb-2">
					<strong style="font-size: 0.9rem;"><i class="bi bi-diagram-3 me-1"></i>Policy Routes</strong>
					<button type="button" class="btn-close ms-auto" style="font-size: 0.6rem;"
						@click="policyRouteModalOpen = false"></button>
				</div>
				<table v-if="policyRouteFiltered.length" class="table table-sm mb-0" style="font-size: 0.8rem;">
					<thead>
						<tr class="text-body-secondary">
							<th>Source</th>
							<th>Destination</th>
							<th>Device</th>
							<th>Table</th>
							<th></th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="rule in policyRouteFiltered" :key="rule.config_name + rule.dest_subnet">
							<td><code>{{ rule.source_subnet }}</code></td>
							<td><code>{{ rule.dest_subnet }}</code></td>
							<td>{{ rule.device }}</td>
							<td>{{ rule.table_id }}</td>
							<td>
								<span v-if="rule.active" class="text-success"><i class="bi bi-check-circle-fill"></i></span>
								<span v-else class="text-secondary"><i class="bi bi-dash-circle"></i></span>
							</td>
						</tr>
					</tbody>
				</table>
				<div v-else class="text-muted text-center py-2">
					<small>No policy routes configured</small>
				</div>
			</div>
		</div>
	</Teleport>
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

tr.gateway-row > td:first-child {
	box-shadow: inset 3px 0 0 0 var(--bs-info);
}
tr.gateway-row {
	background-color: rgba(13, 202, 240, 0.04) !important;
}
tr.server-row > td:first-child {
	box-shadow: inset 3px 0 0 0 var(--bs-success);
}
tr.server-row {
	background-color: rgba(25, 135, 84, 0.04) !important;
}

@media screen and (max-width: 576px) {
	.titleBtn{
		flex-basis: 100%;
	}
}

.policy-route-overlay{
	position: fixed;
	top: 0;
	left: 0;
	width: 100vw;
	height: 100vh;
	z-index: 1060;
}

.policy-route-modal{
	position: fixed;
	background-color: var(--bs-body-bg);
	border: 1px solid var(--bs-border-color);
	min-width: 350px;
	max-width: 550px;
	z-index: 1061;
}

/* Peer table: fixed column widths so the layout doesn't reflow when
   handshake text ("x seconds ago" → "x minutes ago") changes length. */
.peer-table-fixed { table-layout: fixed; }
.peer-table-fixed td,
.peer-table-fixed th {
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}
</style>