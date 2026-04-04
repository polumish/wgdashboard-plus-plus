<script setup>
import {ref, computed, onMounted} from "vue";
import {fetchPost} from "@/utilities/fetch.js";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import LocaleText from "@/components/text/localeText.vue";

const dashboardStore = DashboardConfigurationStore()

const trustedIPs = computed(() => {
	const val = dashboardStore.Configuration?.Security?.trusted_ips
	return val || ''
})

const sessionTimeout = computed(() => {
	const val = dashboardStore.Configuration?.Security?.session_timeout
	return val || '3600'
})

const editValue = ref('')
const editTimeout = ref('3600')
const saving = ref(false)
const savingTimeout = ref(false)

const timeoutOptions = [
	{value: '300', label: '5 Minutes'},
	{value: '1800', label: '30 Minutes'},
	{value: '3600', label: '1 Hour'},
	{value: '28800', label: '8 Hours'},
	{value: '86400', label: '24 Hours'},
	{value: '604800', label: '7 Days'},
	{value: '0', label: 'No Limit'},
]

onMounted(() => {
	editValue.value = trustedIPs.value
	editTimeout.value = sessionTimeout.value
})

const save = async () => {
	saving.value = true
	await fetchPost('/api/updateDashboardConfigurationItem', {
		section: 'Security',
		key: 'trusted_ips',
		value: editValue.value
	}, (res) => {
		if (res.status) {
			dashboardStore.Configuration.Security.trusted_ips = editValue.value
			dashboardStore.newMessage("Server", "Trusted IPs updated", "success")
		} else {
			dashboardStore.newMessage("Server", res.message || "Failed to update", "danger")
		}
		saving.value = false
	})
}

const saveTimeout = async () => {
	savingTimeout.value = true
	await fetchPost('/api/updateDashboardConfigurationItem', {
		section: 'Security',
		key: 'session_timeout',
		value: editTimeout.value
	}, (res) => {
		if (res.status) {
			dashboardStore.Configuration.Security.session_timeout = editTimeout.value
			dashboardStore.newMessage("Server", "Session timeout updated", "success")
		} else {
			dashboardStore.newMessage("Server", res.message || "Failed to update", "danger")
		}
		savingTimeout.value = false
	})
}
</script>

<template>
<div class="card rounded-3">
	<div class="card-header">
		<h6 class="my-2">
			<i class="bi bi-shield-check me-2"></i>
			<LocaleText t="Security"></LocaleText>
		</h6>
	</div>
	<div class="card-body d-flex flex-column gap-3">
		<!-- Trusted IPs -->
		<div>
			<label class="form-label mb-1">
				<small class="fw-bold"><LocaleText t="Trusted IP Addresses"></LocaleText></small>
			</label>
			<p class="text-muted mb-2">
				<small>
					<LocaleText t="Connections from these IPs will skip TOTP verification. Comma-separated IPs or CIDR ranges."></LocaleText>
				</small>
			</p>
			<div class="d-flex gap-2">
				<input type="text" class="form-control form-control-sm rounded-3"
					   v-model="editValue"
					   placeholder="e.g. 192.168.1.0/24, 10.0.0.5">
				<button class="btn btn-sm bg-success-subtle text-success-emphasis rounded-3"
						:disabled="saving || editValue === trustedIPs"
						@click="save()">
					<i class="bi bi-save-fill me-1"></i>
					<LocaleText t="Save"></LocaleText>
				</button>
			</div>
		</div>
		<hr class="my-0">
		<!-- Session Timeout -->
		<div>
			<label class="form-label mb-1">
				<small class="fw-bold"><LocaleText t="Admin Session Timeout"></LocaleText></small>
			</label>
			<p class="text-muted mb-2">
				<small>
					<LocaleText t="How long an admin session stays active without activity."></LocaleText>
				</small>
			</p>
			<div class="d-flex gap-2">
				<select class="form-select form-select-sm rounded-3" style="max-width: 200px;"
						v-model="editTimeout">
					<option v-for="opt in timeoutOptions" :value="opt.value" :key="opt.value">
						{{ opt.label }}
					</option>
				</select>
				<button class="btn btn-sm bg-success-subtle text-success-emphasis rounded-3"
						:disabled="savingTimeout || editTimeout === sessionTimeout"
						@click="saveTimeout()">
					<i class="bi bi-save-fill me-1"></i>
					<LocaleText t="Save"></LocaleText>
				</button>
			</div>
		</div>
	</div>
</div>
</template>
