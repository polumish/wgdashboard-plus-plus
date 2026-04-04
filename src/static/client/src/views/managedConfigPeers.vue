<script setup async>
import {computed, onBeforeUnmount, onMounted, ref} from "vue";
import {clientStore} from "@/stores/clientStore.js";
import {useRoute, useRouter} from "vue-router";

const store = clientStore()
const route = useRoute()
const router = useRouter()
const configName = route.params.configName
const loading = ref(true)
const peers = ref([])
const restricted = ref([])
const showAddModal = ref(false)
const newPeerName = ref('')
const addingPeer = ref(false)
const searchQuery = ref('')
const selectedPeers = ref(new Set())
const refreshInterval = ref(undefined)
const downloadingPeer = ref('')

await store.getClientProfile()

const loadPeers = async () => {
	const data = await store.getManagedConfigPeers(configName)
	if (data) {
		peers.value = data.peers || []
		restricted.value = data.restricted || []
	}
}

onMounted(async () => {
	await loadPeers()
	loading.value = false
	refreshInterval.value = setInterval(loadPeers, 10000)
})

onBeforeUnmount(() => {
	clearInterval(refreshInterval.value)
})

const filteredPeers = computed(() => {
	const q = searchQuery.value.toLowerCase()
	if (!q) return peers.value
	return peers.value.filter(p =>
		p.name.toLowerCase().includes(q) ||
		p.id.toLowerCase().includes(q) ||
		p.allowed_ip.toLowerCase().includes(q)
	)
})

const filteredRestricted = computed(() => {
	const q = searchQuery.value.toLowerCase()
	if (!q) return restricted.value
	return restricted.value.filter(p =>
		p.name.toLowerCase().includes(q) ||
		p.id.toLowerCase().includes(q) ||
		p.allowed_ip.toLowerCase().includes(q)
	)
})

const toggleSelect = (peerId) => {
	if (selectedPeers.value.has(peerId)) {
		selectedPeers.value.delete(peerId)
	} else {
		selectedPeers.value.add(peerId)
	}
}

const selectAll = () => {
	if (selectedPeers.value.size === peers.value.length) {
		selectedPeers.value.clear()
	} else {
		peers.value.forEach(p => selectedPeers.value.add(p.id))
	}
}

const addPeer = async () => {
	addingPeer.value = true
	const result = await store.addManagedPeer(configName, {name: newPeerName.value})
	if (result) {
		newPeerName.value = ''
		showAddModal.value = false
		await loadPeers()
	}
	addingPeer.value = false
}

const deletePeers = async (peerIds) => {
	if (!confirm(`Delete ${peerIds.length} peer(s)?`)) return
	const ok = await store.deleteManagedPeers(configName, peerIds)
	if (ok) {
		selectedPeers.value.clear()
		await loadPeers()
	}
}

const restrictPeers = async (peerIds) => {
	const ok = await store.restrictManagedPeers(configName, peerIds)
	if (ok) {
		selectedPeers.value.clear()
		await loadPeers()
	}
}

const allowPeers = async (peerIds) => {
	const ok = await store.allowManagedPeers(configName, peerIds)
	if (ok) {
		await loadPeers()
	}
}

const downloadPeer = async (peerId) => {
	downloadingPeer.value = peerId
	const data = await store.downloadManagedPeer(configName, peerId)
	if (data) {
		const blob = new Blob([data.file], {type: 'text/plain'})
		const url = URL.createObjectURL(blob)
		const a = document.createElement('a')
		a.href = url
		a.download = `${data.fileName || configName}.conf`
		a.click()
		URL.revokeObjectURL(url)
	}
	downloadingPeer.value = ''
}

const formatBytes = (gb) => {
	if (gb < 0.001) return (gb * 1024 * 1024).toFixed(1) + ' KB'
	if (gb < 1) return (gb * 1024).toFixed(2) + ' MB'
	return gb.toFixed(2) + ' GB'
}

const formatHandshake = (ts) => {
	if (!ts || ts === '0' || ts === 'No Handshake') return 'Never'
	return ts
}

const signingOut = ref(false)
const signOut = async () => {
	signingOut.value = true
	clearInterval(refreshInterval.value)
	const axios = (await import("axios")).default
	const {requestURl} = await import("@/utilities/request.js")
	await axios.get(requestURl('/api/signout')).catch(() => {})
	router.push('/signin')
	store.newNotification("Sign out successful", "success")
}
</script>

<template>
<div class="p-sm-3">
	<!-- Header -->
	<div class="w-100 d-flex align-items-center mb-3">
		<a class="nav-link text-body border-start-0" aria-current="page" href="#">
			<strong>{{ store.clientProfile.Profile.Name || store.clientProfile.Email }}</strong>
		</a>
		<div class="ms-auto px-3 d-flex gap-2 nav-links">
			<RouterLink to="/" class="text-body btn btn-outline-body rounded-3 btn-sm">
				<i class="bi bi-house-fill me-sm-2"></i><span>Home</span>
			</RouterLink>
			<RouterLink to="/managed" class="text-body btn btn-outline-body rounded-3 btn-sm">
				<i class="bi bi-shield-lock me-sm-2"></i><span>Managed</span>
			</RouterLink>
			<a role="button" @click="signOut()" class="btn btn-outline-danger rounded-3 btn-sm"
			   :class="{disabled: signingOut}">
				<i class="bi bi-box-arrow-left me-sm-2"></i>
				<span>{{ signingOut ? 'Signing out...' : 'Sign Out' }}</span>
			</a>
		</div>
	</div>

	<!-- Config Title -->
	<div class="d-flex align-items-center mb-3 px-1">
		<RouterLink to="/managed" class="text-body text-decoration-none me-2">
			<i class="bi bi-arrow-left"></i>
		</RouterLink>
		<h5 class="text-white-50 mb-0">
			<i class="bi bi-hdd-network me-2"></i>{{ configName }}
		</h5>
	</div>

	<!-- Toolbar -->
	<div class="d-flex gap-2 mb-3 flex-wrap">
		<div class="input-group input-group-sm" style="max-width: 300px;">
			<span class="input-group-text bg-transparent border-end-0">
				<i class="bi bi-search"></i>
			</span>
			<input type="text" class="form-control form-control-sm border-start-0"
				   placeholder="Search peers..." v-model="searchQuery">
		</div>
		<button class="btn btn-sm btn-outline-light rounded-3" @click="showAddModal = true">
			<i class="bi bi-plus-lg me-1"></i> Add Peer
		</button>
		<template v-if="selectedPeers.size > 0">
			<button class="btn btn-sm btn-outline-warning rounded-3"
					@click="restrictPeers(Array.from(selectedPeers))">
				<i class="bi bi-lock me-1"></i> Restrict ({{ selectedPeers.size }})
			</button>
			<button class="btn btn-sm btn-outline-danger rounded-3"
					@click="deletePeers(Array.from(selectedPeers))">
				<i class="bi bi-trash me-1"></i> Delete ({{ selectedPeers.size }})
			</button>
		</template>
		<button class="btn btn-sm btn-outline-secondary rounded-3 ms-auto" @click="loadPeers()">
			<i class="bi bi-arrow-clockwise"></i>
		</button>
	</div>

	<!-- Content -->
	<Transition name="app" mode="out-in">
		<div v-if="!loading">
			<!-- Active Peers -->
			<div class="mb-3" v-if="filteredPeers.length > 0">
				<div class="d-flex align-items-center mb-2 px-1">
					<small class="text-muted fw-bold">
						Active Peers ({{ peers.length }})
					</small>
					<a role="button" class="ms-auto text-muted small" @click="selectAll()">
						{{ selectedPeers.size === peers.length ? 'Deselect All' : 'Select All' }}
					</a>
				</div>
				<div class="d-flex flex-column gap-2">
					<div class="card rounded-3 border-0 shadow peer-card"
						 :class="{'border-primary selected': selectedPeers.has(peer.id)}"
						 v-for="peer in filteredPeers" :key="peer.id">
						<div class="card-body p-3">
							<div class="d-flex align-items-center mb-2">
								<div class="form-check me-2">
									<input class="form-check-input" type="checkbox"
										   :checked="selectedPeers.has(peer.id)"
										   @change="toggleSelect(peer.id)">
								</div>
								<div class="d-flex flex-column flex-grow-1 min-width-0">
									<div class="d-flex align-items-center">
										<span class="dot me-2" :class="{active: peer.status === 'running'}"></span>
										<strong class="text-truncate">{{ peer.name || 'Unnamed' }}</strong>
									</div>
									<small class="text-muted text-truncate">
										{{ peer.allowed_ip }}
									</small>
								</div>
								<div class="d-flex gap-1 ms-2">
									<button class="btn btn-sm btn-outline-light rounded-3"
											title="Download config"
											:disabled="downloadingPeer === peer.id"
											@click.stop="downloadPeer(peer.id)">
										<i class="bi" :class="downloadingPeer === peer.id ? 'bi-hourglass-split' : 'bi-download'"></i>
									</button>
									<button class="btn btn-sm btn-outline-warning rounded-3"
											title="Restrict"
											@click.stop="restrictPeers([peer.id])">
										<i class="bi bi-lock"></i>
									</button>
									<button class="btn btn-sm btn-outline-danger rounded-3"
											title="Delete"
											@click.stop="deletePeers([peer.id])">
										<i class="bi bi-trash"></i>
									</button>
								</div>
							</div>
							<div class="d-flex gap-3 ps-4">
								<small class="text-muted">
									<i class="bi bi-arrow-down me-1"></i>{{ formatBytes(peer.total_receive) }}
								</small>
								<small class="text-muted">
									<i class="bi bi-arrow-up me-1"></i>{{ formatBytes(peer.total_sent) }}
								</small>
								<small class="text-muted">
									<i class="bi bi-clock me-1"></i>{{ formatHandshake(peer.latest_handshake) }}
								</small>
								<small class="text-muted" v-if="peer.endpoint">
									<i class="bi bi-geo-alt me-1"></i>{{ peer.endpoint }}
								</small>
							</div>
						</div>
					</div>
				</div>
			</div>

			<!-- Restricted Peers -->
			<div class="mb-3" v-if="filteredRestricted.length > 0">
				<small class="text-muted fw-bold px-1 d-block mb-2">
					Restricted Peers ({{ restricted.length }})
				</small>
				<div class="d-flex flex-column gap-2">
					<div class="card rounded-3 border-0 shadow peer-card border-warning"
						 v-for="peer in filteredRestricted" :key="peer.id">
						<div class="card-body p-3">
							<div class="d-flex align-items-center">
								<div class="d-flex flex-column flex-grow-1 min-width-0">
									<div class="d-flex align-items-center">
										<span class="dot me-2"></span>
										<strong class="text-truncate">{{ peer.name || 'Unnamed' }}</strong>
										<span class="badge text-bg-warning ms-2">Restricted</span>
									</div>
									<small class="text-muted text-truncate">
										{{ peer.allowed_ip }}
									</small>
								</div>
								<div class="d-flex gap-1 ms-2">
									<button class="btn btn-sm btn-outline-success rounded-3"
											title="Allow access"
											@click.stop="allowPeers([peer.id])">
										<i class="bi bi-unlock"></i>
									</button>
									<button class="btn btn-sm btn-outline-danger rounded-3"
											title="Delete"
											@click.stop="deletePeers([peer.id])">
										<i class="bi bi-trash"></i>
									</button>
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>

			<!-- Empty state -->
			<div class="text-center text-muted p-4"
				 v-if="filteredPeers.length === 0 && filteredRestricted.length === 0">
				<i class="bi bi-people d-block mb-2" style="font-size: 2rem;"></i>
				<small v-if="searchQuery">No peers matching "{{ searchQuery }}"</small>
				<small v-else>No peers yet. Click "Add Peer" to create one.</small>
			</div>
		</div>
		<div v-else class="d-flex p-3">
			<div class="bg-body rounded-3 d-flex" style="width: 100%; height: 200px;">
				<div class="spinner-border m-auto"></div>
			</div>
		</div>
	</Transition>

	<!-- Add Peer Modal -->
	<Transition name="app">
		<div v-if="showAddModal" class="modal-overlay" @click.self="showAddModal = false">
			<div class="card rounded-3 border-0 shadow modal-card">
				<div class="card-header bg-transparent border-0 d-flex align-items-center p-3">
					<strong>Add New Peer</strong>
					<button class="btn-close btn-close-white ms-auto" @click="showAddModal = false"></button>
				</div>
				<div class="card-body p-3">
					<div class="mb-3">
						<label class="form-label small text-muted">Peer Name</label>
						<input type="text" class="form-control form-control-sm rounded-3"
							   v-model="newPeerName" placeholder="e.g. laptop-john"
							   @keyup.enter="addPeer()">
					</div>
					<button class="btn btn-primary rounded-3 w-100"
							:disabled="addingPeer"
							@click="addPeer()">
						<span v-if="addingPeer" class="spinner-border spinner-border-sm me-2"></span>
						{{ addingPeer ? 'Adding...' : 'Add Peer' }}
					</button>
				</div>
			</div>
		</div>
	</Transition>
</div>
</template>

<style scoped>
.peer-card {
	background-color: rgba(0, 0, 0, 0.25);
	backdrop-filter: blur(8px);
	transition: transform 0.1s ease;
}
.peer-card.selected {
	border: 1px solid var(--bs-primary) !important;
	background-color: rgba(13, 110, 253, 0.1);
}
.peer-card.border-warning {
	border-left: 3px solid var(--bs-warning) !important;
}

.dot {
	width: 8px;
	height: 8px;
	border-radius: 50%;
	display: inline-block;
	background-color: #6c757d;
	flex-shrink: 0;
}
.dot.active {
	background-color: #28a745;
	box-shadow: 0 0 0 .15rem #28a74545;
}

.min-width-0 {
	min-width: 0;
}

.modal-overlay {
	position: fixed;
	top: 0;
	left: 0;
	width: 100vw;
	height: 100vh;
	background: rgba(0,0,0,0.5);
	display: flex;
	align-items: center;
	justify-content: center;
	z-index: 1050;
}
.modal-card {
	width: 90%;
	max-width: 400px;
	background-color: rgba(30, 30, 30, 0.95);
	backdrop-filter: blur(12px);
}

.input-group-text {
	border-color: rgba(255,255,255,0.15);
}
.input-group .form-control {
	border-color: rgba(255,255,255,0.15);
}

@media screen and (max-width: 576px) {
	.nav-links a span {
		display: none;
	}
}
</style>
