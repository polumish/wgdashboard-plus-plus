<script>
import DashboardSettingsInputWireguardConfigurationPath
	from "@/components/settingsComponent/dashboardSettingsInputWireguardConfigurationPath.vue";
import DashboardSettingsWireguardConfigurationAutostart
	from "@/components/settingsComponent/dashboardSettingsWireguardConfigurationAutostart.vue";
import DashboardWireguardConfigurationTracking
	from "@/components/settingsComponent/dashboardWireguardConfigurationTracking.vue";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {fetchPost} from "@/utilities/fetch.js";
import LocaleText from "@/components/text/localeText.vue";

export default {
	components: {
		LocaleText,
		DashboardSettingsInputWireguardConfigurationPath,
		DashboardSettingsWireguardConfigurationAutostart,
		DashboardWireguardConfigurationTracking
	},
	setup(){
		const store = DashboardConfigurationStore();
		return {store};
	},
	data(){
		return {
			mtuValue: "",
			mtuChanged: false,
			mtuValid: false,
			mtuInvalid: false,
			mtuInvalidMsg: "",
			mtuSaving: false,
			mtuTimeout: undefined
		}
	},
	mounted(){
		this.mtuValue = this.store.Configuration.WireGuardConfiguration?.interface_mtu || "1420";
	},
	methods: {
		async saveMTU(){
			if (!this.mtuChanged) return;
			const val = parseInt(this.mtuValue);
			if (isNaN(val) || val < 576 || val > 9000){
				this.mtuInvalid = true;
				this.mtuInvalidMsg = "MTU must be between 576 and 9000";
				return;
			}
			this.mtuSaving = true;
			await fetchPost("/api/updateDashboardConfigurationItem", {
				section: "WireGuardConfiguration",
				key: "interface_mtu",
				value: this.mtuValue
			}, (res) => {
				if (res.status){
					this.mtuValid = true;
					this.mtuInvalid = false;
					if (this.store.Configuration.WireGuardConfiguration){
						this.store.Configuration.WireGuardConfiguration.interface_mtu = this.mtuValue;
					}
					clearTimeout(this.mtuTimeout);
					this.mtuTimeout = setTimeout(() => this.mtuValid = false, 5000);
				} else {
					this.mtuValid = false;
					this.mtuInvalid = true;
					this.mtuInvalidMsg = res.message;
				}
				this.mtuChanged = false;
				this.mtuSaving = false;
			});
		}
	}
}
</script>

<template>
	<div class="d-flex gap-3 flex-column" >
		<DashboardSettingsInputWireguardConfigurationPath
			targetData="wg_conf_path"
			title="Configurations Directory"
			:warning="true"
			warning-text="Remember to remove / at the end of your path. e.g /etc/wireguard"
		>
		</DashboardSettingsInputWireguardConfigurationPath>
		<div class="card">
			<div class="card-header">
				<h6 class="my-2">
					<LocaleText t="Default Interface MTU"></LocaleText>
				</h6>
			</div>
			<div class="card-body">
				<div class="form-group">
					<label for="interface_mtu_input" class="text-muted mb-1">
						<strong><small>
							<LocaleText t="MTU"></LocaleText>
						</small></strong>
					</label>
					<div class="d-flex gap-2 align-items-start">
						<div class="flex-grow-1">
							<input type="number" class="form-control rounded-3"
								   :class="{'is-invalid': mtuInvalid, 'is-valid': mtuValid}"
								   id="interface_mtu_input"
								   v-model="mtuValue"
								   min="576" max="9000"
								   @input="mtuChanged = true"
								   :disabled="mtuSaving"
							>
							<div class="invalid-feedback fw-bold">{{ mtuInvalidMsg }}</div>
						</div>
						<button
							@click="saveMTU()"
							:disabled="!mtuChanged"
							class="ms-auto btn rounded-3 border-success-subtle bg-success-subtle text-success-emphasis">
							<i class="bi bi-save2-fill" v-if="!mtuSaving"></i>
							<span class="spinner-border spinner-border-sm" v-else></span>
						</button>
					</div>
					<div class="px-2 py-1 text-info-emphasis bg-info-subtle border border-info-subtle rounded-2 d-inline-block mt-1">
						<small>
							<i class="bi bi-info-circle-fill me-2"></i>
							<LocaleText t="Default MTU for new configurations. Does not affect existing ones."></LocaleText>
						</small>
					</div>
				</div>
			</div>
		</div>
		<DashboardSettingsWireguardConfigurationAutostart></DashboardSettingsWireguardConfigurationAutostart>
		<DashboardWireguardConfigurationTracking/>
	</div>
</template>

<style scoped>

</style>