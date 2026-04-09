<script>
import { ref } from 'vue'
import { onClickOutside } from '@vueuse/core'
import "animate.css"
import PeerSettingsDropdown from "@/components/configurationComponents/peerSettingsDropdown.vue";
import LocaleText from "@/components/text/localeText.vue";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {GetLocale} from "@/utilities/locale.js";
import PeerTagBadge from "@/components/configurationComponents/peerTagBadge.vue";

export default {
	name: "peer",
	methods: {GetLocale},
	components: {
		PeerTagBadge, LocaleText, PeerSettingsDropdown
	},
	props: {
		Peer: Object, ConfigurationInfo: Object, order: Number, searchPeersLength: Number, policyRoutes: Array
	},
	setup(){
		const target = ref(null);
		const subMenuOpened = ref(false)
		const routePopoverOpen = ref(false)
		const routePopoverRef = ref(null)
		const dashboardStore = DashboardConfigurationStore()
		onClickOutside(target, event => {
			subMenuOpened.value = false;
		});
		onClickOutside(routePopoverRef, event => {
			routePopoverOpen.value = false;
		});
		return {target, subMenuOpened, dashboardStore, routePopoverOpen, routePopoverRef}
	},
	computed: {
		getLatestHandshake(){
			if (this.Peer.latest_handshake.includes(",")){
				return this.Peer.latest_handshake.split(",")[0]
			}
			return this.Peer.latest_handshake;
		},
		getDropup(){
			return this.searchPeersLength - this.order <= 3
		},
		policyRouteStatus(){
			if (!this.policyRoutes || !(this.Peer.is_gateway === true || this.Peer.is_gateway === 1)) return null
			if (this.policyRoutes.length === 0) return null
			return this.policyRoutes.some(r => r.active) ? 'active' : 'inactive'
		}
	}
}
</script>

<template>
	<div class="card shadow-sm rounded-3 peerCard"
		 :id="'peer_'+Peer.id"
		:class="{'border-warning': Peer.restricted, 'gateway-card': Peer.is_gateway === true || Peer.is_gateway === 1, 'server-card': Peer.is_gateway === 2}">
		<div>
			<div v-if="!Peer.restricted" class="card-header bg-transparent d-flex align-items-center gap-2 border-0">
				<div class="dot ms-0" :class="{active: Peer.status === 'running'}"></div>
				<div
					style="font-size: 0.8rem; color: #28a745"
					class="d-flex align-items-center"
					v-if="dashboardStore.Configuration.Server.dashboard_peer_list_display === 'list' && Peer.status === 'running'">
					<i class="bi bi-box-arrow-in-right me-2"></i>
					<span>
						{{ Peer.endpoint }}
					</span>
				</div>
				
				
				<div style="font-size: 0.8rem" class="ms-auto d-flex gap-2">
					<span class="text-primary">
						<i class="bi bi-arrow-down"></i><strong>
						{{(Peer.cumu_receive + Peer.total_receive).toFixed(4)}}</strong> GB
					</span>
					<span class="text-success">
						<i class="bi bi-arrow-up"></i><strong>
						{{(Peer.cumu_sent + Peer.total_sent).toFixed(4)}}</strong> GB
					</span>
					<span class="text-secondary" v-if="Peer.latest_handshake !== 'No Handshake'">
						<i class="bi bi-arrows-angle-contract"></i>
						{{getLatestHandshake}} ago
					</span>
				</div>
			</div>
			<div v-else class="border-0 card-header bg-transparent text-warning fw-bold" 
			     style="font-size: 0.8rem">
				<i class="bi-lock-fill me-2"></i>
				<LocaleText t="Access Restricted"></LocaleText>
			</div>
		</div>
		<div class="card-body pt-1" style="font-size: 0.9rem">
			<h6>
				<span v-if="Peer.is_gateway === true || Peer.is_gateway === 1" class="badge bg-info-subtle text-info-emphasis rounded-3 me-1" title="Gateway">
					<i class="bi bi-router"></i> GW
				</span>
				<span v-else-if="Peer.is_gateway === 2" class="badge bg-success-subtle text-success-emphasis rounded-3 me-1" title="Server">
					<i class="bi bi-hdd-rack"></i> SRV
				</span>
				<span v-if="policyRouteStatus" class="position-relative d-inline-block">
					<span role="button"
						@click.stop="routePopoverOpen = !routePopoverOpen"
						class="badge rounded-3 me-1"
						:class="policyRouteStatus === 'active' ? 'bg-success-subtle text-success-emphasis' : 'bg-secondary-subtle text-secondary-emphasis'"
						:title="'Policy route ' + policyRouteStatus + ' — click for details'">
						<i class="bi bi-signpost-split"></i> Route
					</span>
					<Transition name="fade">
						<div v-if="routePopoverOpen" ref="routePopoverRef"
							class="policy-route-popover position-absolute shadow rounded-3 p-2"
							style="z-index: 1050; min-width: 280px; left: 0; top: 100%;">
							<div class="d-flex align-items-center mb-2">
								<small class="fw-bold"><i class="bi bi-signpost-split me-1"></i>Policy Routes</small>
								<button class="btn btn-sm btn-close ms-auto" @click.stop="routePopoverOpen = false" style="font-size: 0.5rem;"></button>
							</div>
							<table class="table table-sm table-borderless mb-0" style="font-size: 0.75rem;">
								<thead>
									<tr class="text-muted">
										<th class="py-0">Source</th>
										<th class="py-0">Destination</th>
										<th class="py-0">Table</th>
										<th class="py-0"></th>
									</tr>
								</thead>
								<tbody>
									<tr v-for="rule in policyRoutes" :key="rule.dest_subnet">
										<td class="py-0"><code>{{ rule.source_subnet }}</code></td>
										<td class="py-0"><code>{{ rule.dest_subnet }}</code></td>
										<td class="py-0">{{ rule.table_id }}</td>
										<td class="py-0">
											<span v-if="rule.active" class="text-success"><i class="bi bi-check-circle-fill"></i></span>
											<span v-else class="text-secondary"><i class="bi bi-dash-circle"></i></span>
										</td>
									</tr>
								</tbody>
							</table>
						</div>
					</Transition>
				</span>
				{{Peer.name ? Peer.name : GetLocale('Untitled Peer')}}
			</h6>
			<div class="d-flex"
			     :class="[['grid','columns'].includes(dashboardStore.Configuration.Server.dashboard_peer_list_display) ? 'gap-1 flex-column' : 'flex-row gap-3']">
				<div :class="{'d-flex gap-2 align-items-center' : dashboardStore.Configuration.Server.dashboard_peer_list_display === 'list'}">
					<small class="text-muted">
						<LocaleText t="Allowed IPs"></LocaleText>
					</small>
					<small class="d-block">
						<samp>{{Peer.allowed_ip}}</samp>
					</small>
				</div>
				<div class="d-flex align-items-center gap-1"
					:class="{'ms-auto': dashboardStore.Configuration.Server.dashboard_peer_list_display === 'list'}"
				>
					<PeerTagBadge :BackgroundColor="group.BackgroundColor" :GroupName="group.GroupName" :Icon="'bi-' + group.Icon"
						v-for="group in Object.values(ConfigurationInfo.Info.PeerGroups).filter(x => x.Peers.includes(Peer.id))"
					></PeerTagBadge>
					<div class="ms-auto px-2 rounded-3 subMenuBtn position-relative"
					     :class="{active: this.subMenuOpened}"
					>
						<a role="button" class="text-body"
						   @click="this.subMenuOpened = true">
							<h5 class="mb-0"><i class="bi bi-three-dots"></i></h5>
						</a>
						<Transition name="slide-fade">
							<PeerSettingsDropdown
								:dropup="getDropup"
								@qrcode="this.$emit('qrcode')"
								@configurationFile="this.$emit('configurationFile')"
								@setting="this.$emit('setting')"
								@jobs="this.$emit('jobs')"
								@refresh="this.$emit('refresh')"
								@share="this.$emit('share')"
								@assign="this.$emit('assign')"
								:Peer="Peer"
								:ConfigurationInfo="ConfigurationInfo"
								v-if="this.subMenuOpened"
								ref="target"
							></PeerSettingsDropdown>
						</Transition>
					</div>
				</div>
			</div>
		</div>
		<div class="card-footer" role="button" @click="$emit('details')">
			<small class="d-flex align-items-center">
				<LocaleText t="Details"></LocaleText>
				<i class="bi bi-chevron-right ms-auto"></i>
			</small>
		</div>
	</div>
</template>

<style scoped>



.subMenuBtn.active{
	background-color: #ffffff20;
}

.peerCard{
	transition: box-shadow 0.1s cubic-bezier(0.82, 0.58, 0.17, 0.9);
}

.peerCard:hover{
	box-shadow: var(--bs-box-shadow) !important;
}

.gateway-card{
	border-left: 3px solid var(--bs-info) !important;
	background-color: rgba(13, 202, 240, 0.03);
}
.server-card{
	border-left: 3px solid var(--bs-success) !important;
	background-color: rgba(25, 135, 84, 0.03);
}

.policy-route-popover{
	background-color: var(--bs-body-bg);
	border: 1px solid var(--bs-border-color);
}

.fade-enter-active, .fade-leave-active {
	transition: opacity 0.15s ease;
}
.fade-enter-from, .fade-leave-to {
	opacity: 0;
}
</style>