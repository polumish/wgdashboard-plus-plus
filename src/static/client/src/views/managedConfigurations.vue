<script setup async>
import {computed, onMounted, ref} from "vue";
import {clientStore} from "@/stores/clientStore.js";
import {useRouter} from "vue-router";

const store = clientStore()
const router = useRouter()
const loading = ref(true)

await store.getClientProfile()

onMounted(async () => {
	await store.getManagedConfigurations()
	loading.value = false
})

const configs = computed(() => store.managedConfigurations)

const goToConfig = (name) => {
	router.push(`/managed/${encodeURIComponent(name)}`)
}

const signingOut = ref(false)
const signOut = async () => {
	signingOut.value = true
	const {axiosGet: get, requestURl} = await import("@/utilities/request.js")
	const axios = (await import("axios")).default
	await axios.get(requestURl('/api/signout')).catch(() => {})
	router.push('/signin')
	store.newNotification("Sign out successful", "success")
}
</script>

<template>
<div class="p-sm-3">
	<div class="w-100 d-flex align-items-center mb-3">
		<a class="nav-link text-body border-start-0" aria-current="page" href="#">
			<strong>
				Hi, {{ store.clientProfile.Profile.Name ? store.clientProfile.Profile.Name : store.clientProfile.Email }}
			</strong>
		</a>
		<div class="ms-auto px-3 d-flex gap-2 nav-links">
			<RouterLink to="/" class="text-body btn btn-outline-body rounded-3 btn-sm">
				<i class="bi bi-house-fill me-sm-2"></i>
				<span>Home</span>
			</RouterLink>
			<RouterLink to="/settings" class="text-body btn btn-outline-body rounded-3 btn-sm">
				<i class="bi bi-gear-fill me-sm-2"></i>
				<span>Settings</span>
			</RouterLink>
			<a role="button" @click="signOut()" class="btn btn-outline-danger rounded-3 btn-sm"
			   :class="{disabled: signingOut}">
				<i class="bi bi-box-arrow-left me-sm-2"></i>
				<span>{{ signingOut ? 'Signing out...' : 'Sign Out' }}</span>
			</a>
		</div>
	</div>

	<h5 class="text-white-50 mb-3 px-1">
		<i class="bi bi-shield-lock me-2"></i>Managed Configurations
	</h5>

	<Transition name="app" mode="out-in">
		<div v-if="!loading">
			<div class="d-flex flex-column gap-3" v-if="configs.length > 0">
				<div class="card rounded-3 border-0 shadow" role="button"
					 v-for="config in configs" :key="config.name"
					 @click="goToConfig(config.name)">
					<div class="card-body p-3">
						<div class="d-flex align-items-center mb-2">
							<strong>{{ config.name }}</strong>
							<span class="badge rounded-3 ms-auto"
								  :class="config.status ? 'text-bg-success' : 'text-bg-secondary'">
								{{ config.status ? 'Running' : 'Stopped' }}
							</span>
						</div>
						<div class="d-flex gap-3">
							<small class="text-muted">
								<i class="bi bi-people-fill me-1"></i>
								{{ config.active_peers }} / {{ config.total_peers }} peers
							</small>
							<small class="text-muted">
								<i class="bi bi-hdd-network me-1"></i>
								{{ config.address }}
							</small>
						</div>
					</div>
				</div>
			</div>
			<div class="text-center text-muted p-4" v-else>
				<i class="bi bi-shield-x d-block mb-2" style="font-size: 2rem;"></i>
				<small>No managed configurations assigned to your account</small>
			</div>
		</div>
		<div v-else class="d-flex p-3">
			<div class="bg-body rounded-3 d-flex" style="width: 100%; height: 200px;">
				<div class="spinner-border m-auto"></div>
			</div>
		</div>
	</Transition>
</div>
</template>

<style scoped>
.card {
	background-color: rgba(0, 0, 0, 0.25);
	backdrop-filter: blur(8px);
	transition: transform 0.15s ease, box-shadow 0.15s ease;
	cursor: pointer;
}
.card:hover {
	transform: translateY(-2px);
	box-shadow: 0 4px 15px rgba(0,0,0,0.3) !important;
}

@media screen and (max-width: 576px) {
	.nav-links a span {
		display: none;
	}
}
</style>
