<script setup>
import {onMounted, ref} from "vue";
import {fetchGet, fetchPost} from "@/utilities/fetch.js";
import {useRoute} from "vue-router";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import LocaleText from "@/components/text/localeText.vue";

const route = useRoute()
const store = DashboardConfigurationStore()
const emit = defineEmits(["close", "refreshPeersList"])

const backups = ref([])
const loading = ref(true)
const creating = ref(false)
const confirmRestore = ref(null)   // holds backup name being confirmed
const confirmDelete = ref(null)    // holds backup name being confirmed

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
	const base = window.location.origin
	window.location.href = `${base}/api/backup/config/download?configName=${encodeURIComponent(configName)}&name=${encodeURIComponent(name)}`
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
<div class="peerSettingContainer w-100 h-100 position-absolute top-0 start-0 overflow-y-scroll">
	<div class="d-flex h-100 w-100">
		<div class="modal-dialog-centered dashboardModal w-100 overflow-x-hidden flex-column gap-3 mx-3" style="max-width: 700px;">
			<div class="my-5 d-flex gap-3 flex-column position-relative">

				<!-- Header -->
				<div class="card rounded-3">
					<div class="card-body d-flex align-items-center gap-2" style="padding: var(--density-card-py) var(--density-card-px)">
						<div>
							<h4 class="mb-0 d-flex align-items-center gap-2">
								<i class="bi bi-archive"></i>
								<LocaleText t="Backups"></LocaleText>
								<span class="text-muted">&mdash;</span>
								<samp class="fs-5">{{ configName }}</samp>
							</h4>
						</div>
						<div class="ms-auto d-flex gap-2 align-items-center">
							<button
								@click="createBackup()"
								:disabled="creating"
								class="btn btn-sm bg-success-subtle text-success-emphasis border-success-subtle rounded-3">
								<span v-if="creating" class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>
								<i v-else class="bi bi-plus-circle-fill me-1"></i>
								<LocaleText t="Create"></LocaleText>
							</button>
							<button type="button" class="btn-close" @click="emit('close')"></button>
						</div>
					</div>
				</div>

				<!-- Info bar -->
				<div class="card rounded-3 border-success-subtle bg-success-subtle">
					<div class="card-body py-2 px-3">
						<small class="text-success-emphasis d-flex align-items-center gap-2">
							<i class="bi bi-info-circle-fill"></i>
							<LocaleText t="Backups are created automatically on peer and interface changes (debounced)."></LocaleText>
						</small>
					</div>
				</div>

				<!-- Backup List -->
				<div class="position-relative d-flex flex-column gap-2">
					<TransitionGroup name="list1">
						<div key="spinner" v-if="loading && backups.length === 0" class="text-center py-5">
							<div class="spinner-border text-secondary" role="status"></div>
						</div>

						<div key="empty" v-else-if="!loading && backups.length === 0"
						     class="card rounded-3">
							<div class="card-body text-center text-muted py-4">
								<i class="bi bi-archive me-2"></i>
								<LocaleText t="No backups yet. Click Create to make one."></LocaleText>
							</div>
						</div>

						<div v-for="b in backups" :key="b.name" class="card rounded-3 position-relative">
							<!-- Restore confirmation overlay -->
							<Transition name="zoomReversed">
								<div v-if="confirmRestore === b.name"
								     class="position-absolute w-100 h-100 start-0 top-0 rounded-3 d-flex p-2"
								     style="background: rgba(0,0,0,0.55); backdrop-filter: blur(2px); z-index: 10;">
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

							<!-- Delete confirmation overlay -->
							<Transition name="zoomReversed">
								<div v-if="confirmDelete === b.name"
								     class="position-absolute w-100 h-100 start-0 top-0 rounded-3 d-flex p-2"
								     style="background: rgba(0,0,0,0.55); backdrop-filter: blur(2px); z-index: 10;">
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

							<div class="card-body px-3 py-3">
								<div class="d-flex align-items-start gap-3 flex-wrap">
									<!-- Icon -->
									<i class="bi fs-4 mt-1" :class="typeIcon(b.type)"></i>

									<!-- Details -->
									<div class="flex-grow-1 min-w-0">
										<div class="d-flex align-items-center gap-2 flex-wrap mb-1">
											<samp class="fw-semibold" style="word-break: break-all;">{{ b.name }}</samp>
											<span class="badge rounded-pill border"
											      :class="badgeClass(b.type)"
											      style="font-size: var(--density-font-sm)">
												{{ b.type || 'manual' }}
											</span>
										</div>
										<div v-if="b.event" class="text-muted mb-1">
											<small><i class="bi bi-tag me-1"></i>{{ b.event }}</small>
										</div>
										<div class="d-flex gap-3 flex-wrap">
											<small class="text-muted" v-if="b.date">
												<i class="bi bi-clock me-1"></i>{{ formatDate(b.date) }}
											</small>
											<small class="text-muted" v-if="b.size != null">
												<i class="bi bi-hdd me-1"></i>{{ formatSize(b.size) }}
											</small>
										</div>
									</div>

									<!-- Action buttons -->
									<div class="d-flex gap-1 align-items-center flex-shrink-0">
										<button
											@click="downloadBackup(b.name)"
											class="btn btn-sm bg-primary-subtle text-primary-emphasis border-primary-subtle rounded-3"
											title="Download">
											<i class="bi bi-download"></i>
										</button>
										<button
											@click="confirmRestore = b.name"
											class="btn btn-sm bg-warning-subtle text-warning-emphasis border-warning-subtle rounded-3"
											title="Restore">
											<i class="bi bi-clock-history"></i>
										</button>
										<button
											@click="confirmDelete = b.name"
											class="btn btn-sm bg-danger-subtle text-danger-emphasis border-danger-subtle rounded-3"
											title="Delete">
											<i class="bi bi-trash-fill"></i>
										</button>
									</div>
								</div>
							</div>
						</div>
					</TransitionGroup>
				</div>

			</div>
		</div>
	</div>
</div>
</template>

<style scoped>
.dashboardModal {
	width: 100%;
}

@media screen and (min-width: 700px) {
	.dashboardModal {
		width: 700px;
	}
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
