<script setup>
import {ref, onMounted} from "vue";
import {fetchGet} from "@/utilities/fetch.js";

const rules = ref([])
const loading = ref(true)

function loadStatus() {
    loading.value = true
    fetchGet("/api/policyRouting/status", {}, (res) => {
        if (res.status) {
            rules.value = res.data
        }
        loading.value = false
    })
}

onMounted(loadStatus)
</script>

<template>
<div class="card shadow-sm rounded-3">
    <div class="card-header d-flex align-items-center justify-content-between">
        <h6 class="mb-0">
            <i class="bi bi-signpost-split me-2"></i>Policy Routing Rules
        </h6>
        <button class="btn btn-sm btn-outline-secondary" @click="loadStatus" :disabled="loading">
            <i class="bi bi-arrow-clockwise" :class="{'spin': loading}"></i>
        </button>
    </div>
    <div class="card-body">
        <div v-if="loading" class="text-center py-3">
            <div class="spinner-border spinner-border-sm"></div>
        </div>
        <div v-else-if="rules.length === 0" class="text-muted text-center py-3">
            <i class="bi bi-info-circle me-1"></i>
            No policy routes. Add a gateway peer to enable automatic source-based routing.
        </div>
        <div v-else class="table-responsive">
            <table class="table table-sm table-hover mb-0">
                <thead>
                    <tr>
                        <th>Source</th>
                        <th>Destination</th>
                        <th>Device</th>
                        <th>Table ID</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-for="rule in rules" :key="rule.config_name + rule.dest_subnet">
                        <td><code>{{ rule.source_subnet }}</code></td>
                        <td><code>{{ rule.dest_subnet }}</code></td>
                        <td>{{ rule.device }}</td>
                        <td>{{ rule.table_id }}</td>
                        <td>
                            <span v-if="rule.active" class="badge bg-success">Active</span>
                            <span v-else class="badge bg-secondary">Inactive</span>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</div>
</template>

<style scoped>
.spin {
    animation: spin 1s linear infinite;
}
@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
</style>
