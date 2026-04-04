<script>
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {fetchPost} from "@/utilities/fetch.js";
import LocaleText from "@/components/text/localeText.vue";

export default {
	name: "dashboardDensity",
	components: {LocaleText},
	setup(){
		const dashboardConfigurationStore = DashboardConfigurationStore();
		return {dashboardConfigurationStore}
	},
	methods: {
		async switchDensity(value){
			await fetchPost("/api/updateDashboardConfigurationItem", {
				section: "Server",
				key: "dashboard_density",
				value: value
			}, (res) => {
				if (res.status){
					this.dashboardConfigurationStore.Configuration.Server.dashboard_density = value;
				}
			});
		}
	}
}
</script>

<template>
	<div>
		<small class="text-muted mb-1 d-block">
			<strong>
				<LocaleText t="Display Density"></LocaleText>
			</strong>
		</small>
		<div class="d-flex gap-1">
			<button class="btn bg-primary-subtle text-primary-emphasis flex-grow-1"
			        @click="this.switchDensity('compact')"
			        :class="{active: this.dashboardConfigurationStore.Configuration.Server.dashboard_density === 'compact'}">
				<i class="bi bi-distribute-horizontal me-2"></i>
				Compact
			</button>
			<button class="btn bg-primary-subtle text-primary-emphasis flex-grow-1"
			        @click="this.switchDensity('normal')"
			        :class="{active: this.dashboardConfigurationStore.Configuration.Server.dashboard_density === 'normal' || !this.dashboardConfigurationStore.Configuration.Server.dashboard_density}">
				<i class="bi bi-distribute-vertical me-2"></i>
				Normal
			</button>
			<button class="btn bg-primary-subtle text-primary-emphasis flex-grow-1"
			        @click="this.switchDensity('comfortable')"
			        :class="{active: this.dashboardConfigurationStore.Configuration.Server.dashboard_density === 'comfortable'}">
				<i class="bi bi-arrows-expand me-2"></i>
				Comfortable
			</button>
		</div>
	</div>
</template>

<style scoped>
</style>
