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

const editValue = ref('')
const saving = ref(false)

onMounted(() => {
	editValue.value = trustedIPs.value
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
</script>

<template>
<div class="card rounded-3">
	<div class="card-header">
		<h6 class="my-2">
			<i class="bi bi-shield-check me-2"></i>
			<LocaleText t="Trusted IP Addresses"></LocaleText>
		</h6>
	</div>
	<div class="card-body d-flex flex-column gap-2">
		<p class="text-muted mb-0">
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
</div>
</template>
