<script setup>
import {ref, computed, onMounted, watch} from "vue";
import {fetchGet, fetchPost} from "@/utilities/fetch.js";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {WireguardConfigurationsStore} from "@/stores/WireguardConfigurationsStore.js";
import LocaleText from "@/components/text/localeText.vue";

const props = defineProps(['client'])
const dashboardStore = DashboardConfigurationStore()
const wireguardStore = WireguardConfigurationsStore()

const accesses = ref([])
const loading = ref(true)
const granting = ref(false)
const selectedConfig = ref('')
const selectedRole = ref('manager')

const loadAccesses = async () => {
	loading.value = true
	await fetchGet('/api/clients/getConfigAccess', {
		ClientID: props.client.ClientID
	}, (res) => {
		if (res.status) {
			accesses.value = res.data || []
		}
	})
	loading.value = false
}

onMounted(() => loadAccesses())
watch(() => props.client?.ClientID, () => loadAccesses())

const availableConfigs = computed(() => {
	const grantedNames = accesses.value.map(a => a.ConfigurationName)
	return wireguardStore.Configurations
		.map(c => c.Name)
		.filter(name => !grantedNames.includes(name))
})

const grantAccess = async () => {
	if (!selectedConfig.value) return
	granting.value = true
	await fetchPost('/api/clients/grantConfigAccess', {
		ClientID: props.client.ClientID,
		ConfigurationName: selectedConfig.value,
		Role: selectedRole.value
	}, async (res) => {
		if (res.status) {
			dashboardStore.newMessage("Server", "Config access granted", "success")
			selectedConfig.value = ''
			await loadAccesses()
		} else {
			dashboardStore.newMessage("Server", res.message || "Failed to grant access", "danger")
		}
		granting.value = false
	})
}

const revokeAccess = async (accessId) => {
	await fetchPost('/api/clients/revokeConfigAccess', {
		AccessID: accessId
	}, async (res) => {
		if (res.status) {
			dashboardStore.newMessage("Server", "Config access revoked", "success")
			await loadAccesses()
		} else {
			dashboardStore.newMessage("Server", "Failed to revoke access", "danger")
		}
	})
}
</script>

<template>
<div class="d-flex flex-column border-bottom pb-1">
	<div class="d-flex flex-column p-3 gap-3">
		<div class="d-flex align-items-center">
			<h6 class="mb-0">
				<LocaleText t="Configuration Access"></LocaleText>
				<span class="text-bg-primary badge ms-2">
					{{ accesses.length }}
				</span>
			</h6>
		</div>

		<!-- Current Accesses -->
		<div class="rounded-3 border overflow-hidden" v-if="!loading">
			<div class="list-group list-group-flush" v-if="accesses.length > 0">
				<div class="list-group-item d-flex align-items-center gap-2"
					 v-for="access in accesses" :key="access.AccessID">
					<div class="d-flex flex-column flex-grow-1">
						<span class="fw-bold">{{ access.ConfigurationName }}</span>
						<small class="text-muted">
							<LocaleText t="Role"></LocaleText>:
							<span class="badge rounded-3"
								  :class="access.Role === 'manager' ? 'text-bg-warning' : 'text-bg-info'">
								{{ access.Role }}
							</span>
							&middot;
							<LocaleText t="Granted"></LocaleText>: {{ access.GrantedDate }}
						</small>
					</div>
					<button class="btn btn-sm bg-danger-subtle text-danger-emphasis rounded-3"
							@click="revokeAccess(access.AccessID)"
							title="Revoke access">
						<i class="bi bi-x-lg"></i>
					</button>
				</div>
			</div>
			<div class="p-3 text-center text-muted" v-else>
				<small><LocaleText t="No configuration access granted"></LocaleText></small>
			</div>
		</div>
		<div v-else class="placeholder-glow">
			<div class="placeholder w-100 rounded-3" style="height: 60px"></div>
		</div>

		<!-- Grant New Access -->
		<div class="d-flex gap-2 align-items-end" v-if="availableConfigs.length > 0">
			<div class="flex-grow-1">
				<label class="form-label mb-1">
					<small class="text-muted"><LocaleText t="Configuration"></LocaleText></small>
				</label>
				<select class="form-select form-select-sm rounded-3" v-model="selectedConfig">
					<option value="" disabled>Select configuration...</option>
					<option v-for="name in availableConfigs" :value="name" :key="name">
						{{ name }}
					</option>
				</select>
			</div>
			<div>
				<label class="form-label mb-1">
					<small class="text-muted"><LocaleText t="Role"></LocaleText></small>
				</label>
				<select class="form-select form-select-sm rounded-3" v-model="selectedRole">
					<option value="viewer">Viewer</option>
					<option value="manager">Manager</option>
				</select>
			</div>
			<button class="btn btn-sm bg-success-subtle text-success-emphasis rounded-3"
					:disabled="!selectedConfig || granting"
					@click="grantAccess()">
				<i class="bi bi-plus-lg me-1"></i>
				<LocaleText t="Grant"></LocaleText>
			</button>
		</div>
	</div>
</div>
</template>
