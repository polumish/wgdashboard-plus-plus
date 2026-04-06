<script setup>
import {onMounted, ref} from "vue";
import {fetchGet, fetchPost, getUrl} from "@/utilities/fetch.js";
import {useRoute} from "vue-router";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import LocaleText from "@/components/text/localeText.vue";

const route = useRoute()
const store = DashboardConfigurationStore()
const emit = defineEmits(["close", "refreshPeersList"])

const backups = ref([])
const loading = ref(true)
const creating = ref(false)
const confirmRestore = ref(null)
const confirmDelete = ref(null)

const configName = route.params.id

const loadBackups = () => {
	loading.value = true
	fetchGet("/api/backup/config/list", {configName}, (res) => {
		loading.value = false
		if (res.status) {
			backups.value = res.data
		} else {
			store.newMessage("Server", res.message || "Failed to load backups", "danger")
		}
	})
}

const createBackup = () => {
	creating.value = true
	fetchGet("/api/backup/config/create", {configName}, (res) => {
		creating.value = false
		if (res.status) {
			store.newMessage("Server", "Backup created", "success")
			loadBackups()
		} else {
			store.newMessage("Server", res.message || "Failed to create backup", "danger")
		}
	})
}

const deleteBackup = (name) => {
	confirmDelete.value = null
	fetchPost("/api/backup/config/delete", {configName, name}, (res) => {
		if (res.status) {
			store.newMessage("Server", "Backup deleted", "success")
			backups.value = backups.value.filter(b => b.name !== name)
		} else {
			store.newMessage("Server", res.message || "Failed to delete backup", "danger")
		}
	})
}

const downloadBackup = (name) => {
	window.location.href = getUrl(`/api/backup/config/download?configName=${encodeURIComponent(configName)}&name=${encodeURIComponent(name)}`)
}

const restoreBackup = (name) => {
	confirmRestore.value = null
	fetchPost("/api/backup/config/restore", {configName, name}, (res) => {
		if (res.status) {
			store.newMessage("Server", "Backup restored successfully", "success")
			emit("refreshPeersList")
		} else {
			store.newMessage("Server", res.message || "Failed to restore backup", "danger")
		}
	})
}

const formatDate = (dateStr) => {
	if (!dateStr) return ""
	try {
		return new Date(dateStr).toLocaleString()
	} catch {
		return dateStr
	}
}

const formatSize = (bytes) => {
	if (bytes == null) return ""
	if (bytes < 1024) return bytes + " B"
	if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB"
	return (bytes / (1024 * 1024)).toFixed(1) + " MB"
}

const badgeClass = (type) => {
	if (type === "auto") return "text-success-emphasis bg-success-subtle border-success-subtle"
	if (type === "global") return "text-primary-emphasis bg-primary-subtle border-primary-subtle"
	return "text-secondary-emphasis bg-secondary-subtle border-secondary-subtle"
}

const typeIcon = (type) => {
	if (type === "auto") return "bi-lightning-fill text-warning"
	if (type === "global") return "bi-calendar-check text-primary"
	return "bi-archive text-secondary"
}

onMounted(() => {
	loadBackups()
})
</script>

<template>
<div class="peerSettingContainer backups-overlay w-100 h-100 position-absolute top-0 start-0 overflow-y-scroll"
     @click.self="emit('close')">
	<div class="container d-flex h-100 w-100">
		<div class="m-auto modal-dialog-centered backup-panel">
			<div class="card rounded-3 shadow-lg">
				<!-- Header -->
				<div class="card-header bg-transparent border-bottom d-flex align-items-center"
				     style="padding: var(--density-card-py) var(--density-card-px)">
					<i class="bi bi-archive me-2" style="font-size: 1.1rem"></i>
					<h5 class="mb-0 d-flex align-items-center gap-2">
						<LocaleText t="Backups"></LocaleText>
						<span class="text-muted fw-normal">&mdash;</span>
						<samp>{{ configName }}</samp>
					</h5>
					<div class="ms-auto d-flex gap-2 align-items-center">
						<button
							@click="createBackup()"
							:disabled="creating"
							class="btn btn-sm bg-success-subtle text-success-emphasis border-success-subtle rounded-3">
							<span v-if="creating" class="spinner-border spinner-border-sm me-1"></span>
							<i v-else class="bi bi-plus-circle-fill me-1"></i>
							<LocaleText t="Create"></LocaleText>
						</button>
						<button type="button" class="btn-close" @click="emit('close')"></button>
					</div>
				</div>

				<!-- Info bar -->
				<div class="border-bottom px-3 py-2 d-flex align-items-center gap-2"
				     style="background: var(--bs-success-bg-subtle); font-size: var(--density-font-sm)">
					<i class="bi bi-info-circle-fill text-success"></i>
					<span class="text-success-emphasis">
						<LocaleText t="Backups are created automatically on peer and interface changes (debounced)."></LocaleText>
					</span>
				</div>

				<!-- Content -->
				<div class="card-body p-0">
					<!-- Loading -->
					<div v-if="loading && backups.length === 0" class="text-center py-5">
						<div class="spinner-border text-secondary" role="status"></div>
					</div>

					<!-- Empty -->
					<div v-else-if="!loading && backups.length === 0" class="text-center text-muted py-5">
						<i class="bi bi-archive" style="font-size: 2rem; opacity: 0.3"></i>
						<p class="mt-2 mb-0">
							<LocaleText t="No backups yet. Click Create to make one."></LocaleText>
						</p>
					</div>

					<!-- Backup list -->
					<div v-else>
						<TransitionGroup name="list1" tag="div">
							<div v-for="(b, idx) in backups" :key="b.name"
							     class="backup-row position-relative"
							     :class="{ 'border-bottom': idx < backups.length - 1 }">

								<!-- Restore confirmation -->
								<Transition name="zoomReversed">
									<div v-if="confirmRestore === b.name"
									     class="confirm-overlay rounded-0 d-flex">
										<div class="m-auto text-center">
											<p class="text-white fw-semibold mb-3">
												<LocaleText t="Restore this backup? Current config will be overwritten."></LocaleText>
											</p>
											<div class="d-flex gap-2 justify-content-center">
												<button class="btn btn-success rounded-3" @click="restoreBackup(b.name)">
													<LocaleText t="Yes, restore"></LocaleText>
												</button>
												<button class="btn bg-secondary-subtle text-secondary-emphasis border-secondary-subtle rounded-3"
												        @click="confirmRestore = null">
													<LocaleText t="Cancel"></LocaleText>
												</button>
											</div>
										</div>
									</div>
								</Transition>

								<!-- Delete confirmation -->
								<Transition name="zoomReversed">
									<div v-if="confirmDelete === b.name"
									     class="confirm-overlay rounded-0 d-flex">
										<div class="m-auto text-center">
											<p class="text-white fw-semibold mb-3">
												<LocaleText t="Delete this backup permanently?"></LocaleText>
											</p>
											<div class="d-flex gap-2 justify-content-center">
												<button class="btn btn-danger rounded-3" @click="deleteBackup(b.name)">
													<LocaleText t="Yes, delete"></LocaleText>
												</button>
												<button class="btn bg-secondary-subtle text-secondary-emphasis border-secondary-subtle rounded-3"
												        @click="confirmDelete = null">
													<LocaleText t="Cancel"></LocaleText>
												</button>
											</div>
										</div>
									</div>
								</Transition>

								<div class="d-flex align-items-center gap-3 flex-wrap"
								     style="padding: var(--density-card-py) var(--density-card-px)">
									<i class="bi" :class="typeIcon(b.type)" style="font-size: 1.1rem"></i>

									<div class="flex-grow-1 min-w-0">
										<div class="d-flex align-items-center gap-2 flex-wrap">
											<samp class="fw-semibold" style="font-size: var(--density-font); word-break: break-all;">{{ b.name }}</samp>
											<span class="badge rounded-pill border"
											      :class="badgeClass(b.type)"
											      style="font-size: var(--density-font-sm)">
												{{ b.type || 'manual' }}
											</span>
										</div>
										<div class="d-flex gap-3 flex-wrap mt-1" style="font-size: var(--density-font-sm)">
											<span v-if="b.event" class="text-muted">
												<i class="bi bi-tag me-1"></i>{{ b.event }}
											</span>
											<span class="text-muted" v-if="b.date">
												<i class="bi bi-clock me-1"></i>{{ formatDate(b.date) }}
											</span>
											<span class="text-muted" v-if="b.size != null">
												<i class="bi bi-hdd me-1"></i>{{ formatSize(b.size) }}
											</span>
										</div>
									</div>

									<div class="d-flex gap-1 align-items-center flex-shrink-0">
										<button @click="downloadBackup(b.name)"
										        class="btn btn-sm bg-primary-subtle text-primary-emphasis border-primary-subtle rounded-3"
										        title="Download">
											<i class="bi bi-download"></i>
										</button>
										<button @click="confirmRestore = b.name"
										        class="btn btn-sm bg-warning-subtle text-warning-emphasis border-warning-subtle rounded-3"
										        title="Restore">
											<i class="bi bi-clock-history"></i>
										</button>
										<button @click="confirmDelete = b.name"
										        class="btn btn-sm bg-danger-subtle text-danger-emphasis border-danger-subtle rounded-3"
										        title="Delete">
											<i class="bi bi-trash-fill"></i>
										</button>
									</div>
								</div>
							</div>
						</TransitionGroup>
					</div>
				</div>
			</div>
		</div>
	</div>
</div>
</template>

<style scoped>
.backups-overlay {
	background-color: rgba(0, 0, 0, 0.85) !important;
	backdrop-filter: blur(8px) !important;
	-webkit-backdrop-filter: blur(8px) !important;
}

[data-bs-theme="light"] .backups-overlay {
	background-color: rgba(240, 242, 245, 0.95) !important;
}

.backup-panel {
	width: 700px;
}

@media screen and (max-width: 750px) {
	.backup-panel {
		width: 100%;
		margin: 0.5rem;
	}
}

.backup-row {
	transition: background-color 0.15s;
}

.backup-row:hover {
	background-color: rgba(255, 255, 255, 0.03);
}

[data-bs-theme="light"] .backup-row:hover {
	background-color: rgba(0, 0, 0, 0.02);
}

.confirm-overlay {
	position: absolute;
	width: 100%;
	height: 100%;
	top: 0;
	left: 0;
	background: rgba(0, 0, 0, 0.6);
	backdrop-filter: blur(2px);
	z-index: 10;
}

.list1-move,
.list1-enter-active,
.list1-leave-active {
	transition: all 0.4s cubic-bezier(0.42, 0, 0.22, 1.0);
}

.list1-enter-from,
.list1-leave-to {
	opacity: 0;
	transform: translateY(20px);
}

.list1-leave-active {
	width: 100%;
	position: absolute;
}
</style>
