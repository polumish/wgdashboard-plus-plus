<script setup>
import {ref, onMounted, computed} from "vue";
import {fetchGet} from "@/utilities/fetch.js";
import {RouterLink} from "vue-router";
import LocaleText from "@/components/text/localeText.vue";

const gateways = ref([])
const loaded = ref(false)
const filter = ref('')

const fetchGateways = () => {
	fetchGet("/api/getAllGateways", {}, (res) => {
		if (res.status) {
			gateways.value = res.data || []
		}
		loaded.value = true
	})
}

const filtered = computed(() => {
	const q = filter.value.trim().toLowerCase()
	if (!q) return gateways.value
	return gateways.value.filter(g =>
		(g.name || '').toLowerCase().includes(q) ||
		(g.configName || '').toLowerCase().includes(q) ||
		(g.allowed_ip || '').toLowerCase().includes(q))
})

const byConfig = computed(() => {
	const m = {}
	for (const g of gateways.value) {
		m[g.configName] = (m[g.configName] || 0) + 1
	}
	return m
})

onMounted(fetchGateways)
</script>

<template>
	<div class="mt-md-5 mt-3 text-body">
		<div class="container-fluid">
			<div class="d-flex align-items-center mb-4 gap-2">
				<h3 class="mb-0">
					<i class="bi bi-router me-2"></i>
					<LocaleText t="Gateways"></LocaleText>
				</h3>
				<button class="btn btn-sm btn-body rounded-3 ms-auto" @click="fetchGateways()">
					<i class="bi bi-arrow-clockwise"></i>
				</button>
			</div>

			<div v-if="!loaded" class="text-center text-muted py-5">
				<div class="spinner-border spinner-border-sm me-2"></div>
				<LocaleText t="Loading..."></LocaleText>
			</div>

			<div v-else-if="gateways.length === 0" class="alert alert-info rounded-3">
				<i class="bi bi-info-circle-fill me-2"></i>
				<LocaleText t="No gateway peers yet. Create one from a WireGuard configuration → Add OPNsense Gateway, or mark an existing peer as gateway from its settings."></LocaleText>
			</div>

			<div v-else>
				<div class="d-flex gap-2 mb-3 flex-wrap">
					<div class="badge bg-body-tertiary text-body-emphasis rounded-3 p-2"
						 v-for="(count, cfg) in byConfig" :key="cfg">
						<i class="bi bi-hdd-network me-1"></i>
						<strong>{{ cfg }}</strong>: {{ count }}
					</div>
				</div>

				<div class="mb-3">
					<input type="text" class="form-control rounded-3" v-model="filter"
						   placeholder="Filter by name, config, or IP...">
				</div>

				<div class="card rounded-3 shadow-sm">
					<div class="table-responsive">
						<table class="table table-hover align-middle mb-0">
							<thead class="table-light">
								<tr>
									<th style="width: 20px;"></th>
									<th><small><LocaleText t="Name"></LocaleText></small></th>
									<th><small><LocaleText t="Configuration"></LocaleText></small></th>
									<th><small><LocaleText t="Tunnel IP"></LocaleText></small></th>
									<th><small><LocaleText t="Reachable Networks"></LocaleText></small></th>
									<th><small><LocaleText t="Last Handshake"></LocaleText></small></th>
									<th style="width: 30px;"></th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="g in filtered" :key="g.configName + '|' + g.id">
									<td>
										<span class="d-inline-block rounded-circle"
											  :style="{width:'10px',height:'10px',backgroundColor: g.status==='running' ? '#28a745' : '#6c757d'}"></span>
									</td>
									<td><strong>{{ g.name || 'Untitled' }}</strong></td>
									<td>
										<RouterLink :to="`/configuration/${g.configName}/peers`"
													class="text-decoration-none">
											<code>{{ g.configName }}</code>
										</RouterLink>
									</td>
									<td><small><samp>{{ g.allowed_ip }}</samp></small></td>
									<td><small class="text-muted"><samp>{{ g.endpoint_allowed_ip }}</samp></small></td>
									<td><small class="text-muted">{{ g.latest_handshake || 'N/A' }}</small></td>
									<td>
										<RouterLink :to="`/configuration/${g.configName}/peers`"
													class="btn btn-sm btn-body rounded-3" title="Open in config">
											<i class="bi bi-box-arrow-up-right"></i>
										</RouterLink>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>
