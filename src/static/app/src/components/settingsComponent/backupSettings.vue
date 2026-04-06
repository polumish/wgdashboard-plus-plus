<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { fetchGet, fetchPost } from "@/utilities/fetch.js";
import LocaleText from "@/components/text/localeText.vue";
import dayjs from "dayjs";

// ─── State ────────────────────────────────────────────────────────────────────

const backups = ref([]);
const settings = ref({
    backup_path: "",
    backup_max_size: 1024,
    backup_auto_on_config_change: true,
    backup_auto_on_settings_change: true,
    backup_auto_debounce: 30,
    backup_daily_enabled: false,
    backup_daily_time: "02:00",
    backup_daily_keep: 7,
    backup_weekly_enabled: false,
    backup_weekly_day: "monday",
    backup_weekly_time: "02:00",
    backup_weekly_keep: 4,
    backup_monthly_enabled: false,
    backup_monthly_day: 1,
    backup_monthly_time: "02:00",
    backup_monthly_keep: 3,
});

const loading = ref(false);
const backupsLoading = ref(false);
const storageExpanded = ref(false);
const activeFilter = ref("all");
const viewMode = ref("table"); // "table" | "calendar"

// Calendar state
const calendarDate = ref(dayjs());
const selectedDay = ref(null);

// Restore modal state
const restoreModal = ref(false);
const restoreTarget = ref(null);
const restoreComponents = ref({
    wireguard_configurations: true,
    dashboard_settings: true,
    webhooks: true,
    peer_jobs: true,
    share_links: true,
    client_portal: true,
    api_keys: true,
});

// Storage info (from settings if available)
const storageUsed = ref(0);
const storageMax = ref(1024);

// Debounce timer for settings auto-save
let saveTimer = null;

// ─── Computed ─────────────────────────────────────────────────────────────────

const filteredBackups = computed(() => {
    if (activeFilter.value === "all") return backups.value;
    return backups.value.filter(b => b.type === activeFilter.value);
});

const backupCountByType = computed(() => {
    const counts = { daily: 0, weekly: 0, monthly: 0, auto: 0, manual: 0 };
    for (const b of backups.value) {
        if (counts[b.type] !== undefined) counts[b.type]++;
        else counts.manual = (counts.manual || 0) + 1;
    }
    return counts;
});

const storagePercent = computed(() => {
    if (!storageMax.value) return 0;
    return Math.min(100, Math.round((storageUsed.value / storageMax.value) * 100));
});

const storageBarClass = computed(() => {
    if (storagePercent.value > 85) return "bg-danger";
    if (storagePercent.value > 60) return "bg-warning";
    return "bg-success";
});

const lastBackup = computed(() => {
    if (!backups.value.length) return null;
    return backups.value.reduce((a, b) => (dayjs(a.date).isAfter(dayjs(b.date)) ? a : b));
});

const restoreSelectedCount = computed(() => {
    return Object.values(restoreComponents.value).filter(Boolean).length;
});

const allRestoreSelected = computed(() => {
    return Object.values(restoreComponents.value).every(Boolean);
});

// Calendar helpers
const calendarDays = computed(() => {
    const start = calendarDate.value.startOf("month");
    const end = calendarDate.value.endOf("month");
    const days = [];
    // pad start
    for (let i = 0; i < start.day(); i++) {
        days.push(null);
    }
    for (let d = start; d.isBefore(end) || d.isSame(end, "day"); d = d.add(1, "day")) {
        days.push(d);
    }
    return days;
});

const backupsByDay = computed(() => {
    const map = {};
    for (const b of backups.value) {
        const key = dayjs(b.date).format("YYYY-MM-DD");
        if (!map[key]) map[key] = [];
        map[key].push(b);
    }
    return map;
});

const selectedDayBackups = computed(() => {
    if (!selectedDay.value) return [];
    const key = selectedDay.value.format("YYYY-MM-DD");
    return backupsByDay.value[key] || [];
});

const weekDays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// ─── Methods ──────────────────────────────────────────────────────────────────

function loadBackups() {
    backupsLoading.value = true;
    fetchGet("/api/backup/global/list", { filter: "all" }, (res) => {
        backupsLoading.value = false;
        if (res && res.status) {
            backups.value = res.data || [];
            // Compute storage used from backup sizes
            const used = backups.value.reduce((acc, b) => acc + (b.size || 0), 0);
            storageUsed.value = Math.round(used / (1024 * 1024)); // MB
        }
    });
}

function loadSettings() {
    fetchGet("/api/backup/settings", {}, (res) => {
        if (res && res.status && res.data) {
            Object.assign(settings.value, res.data);
            storageMax.value = settings.value.backup_max_size || 1024;
        }
    });
}

function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
        fetchPost("/api/backup/settings/update", settings.value, (res) => {
            if (res && res.status) {
                storageMax.value = settings.value.backup_max_size || 1024;
            }
        });
    }, 500);
}

function createSnapshot() {
    loading.value = true;
    fetchGet("/api/backup/global/create", {}, (res) => {
        loading.value = false;
        if (res && res.status) {
            loadBackups();
        }
    });
}

function deleteBackup(name) {
    if (!confirm("Delete this backup?")) return;
    fetchPost("/api/backup/global/delete", { name }, (res) => {
        if (res && res.status) {
            loadBackups();
        }
    });
}

function downloadBackup(name) {
    const url = `/api/backup/global/download?name=${encodeURIComponent(name)}`;
    window.location = url;
}

function openRestoreModal(backup) {
    restoreTarget.value = backup;
    // reset to all selected
    Object.keys(restoreComponents.value).forEach(k => (restoreComponents.value[k] = true));
    restoreModal.value = true;
}

function closeRestoreModal() {
    restoreModal.value = false;
    restoreTarget.value = null;
}

function toggleAllRestore() {
    const newVal = !allRestoreSelected.value;
    Object.keys(restoreComponents.value).forEach(k => (restoreComponents.value[k] = newVal));
}

function doRestore() {
    if (!restoreTarget.value) return;
    const components = Object.entries(restoreComponents.value)
        .filter(([, v]) => v)
        .map(([k]) => k);
    fetchPost("/api/backup/global/restore", { name: restoreTarget.value.name, components }, (res) => {
        if (res && res.status) {
            closeRestoreModal();
            loadBackups();
        }
    });
}

function typeBadgeClass(type) {
    switch (type) {
        case "daily": return "bg-success-subtle text-success-emphasis border-success-subtle";
        case "weekly": return "bg-warning-subtle text-warning-emphasis border-warning-subtle";
        case "monthly": return "bg-info-subtle text-info-emphasis border-info-subtle";
        case "auto": return "bg-orange-subtle text-orange-emphasis border-orange-subtle";
        default: return "bg-secondary-subtle text-secondary-emphasis border-secondary-subtle";
    }
}

function dotClass(type) {
    switch (type) {
        case "daily": return "bg-success";
        case "weekly": return "bg-warning";
        case "monthly": return "bg-info";
        case "auto": return "bg-orange";
        default: return "bg-secondary";
    }
}

function formatSize(bytes) {
    if (!bytes) return "—";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(2) + " MB";
}

function formatDate(d) {
    return d ? dayjs(d).format("YYYY-MM-DD HH:mm") : "—";
}

function calendarDayClick(day) {
    if (!day) return;
    if (selectedDay.value && selectedDay.value.isSame(day, "day")) {
        selectedDay.value = null;
    } else {
        selectedDay.value = day;
    }
}

function prevMonth() {
    calendarDate.value = calendarDate.value.subtract(1, "month");
    selectedDay.value = null;
}

function nextMonth() {
    calendarDate.value = calendarDate.value.add(1, "month");
    selectedDay.value = null;
}

// Watch settings fields for auto-save
watch(
    settings,
    () => {
        scheduleSave();
    },
    { deep: true }
);

onMounted(() => {
    loadSettings();
    loadBackups();
});
</script>

<template>
    <div class="d-flex flex-column" :style="{ gap: 'var(--density-gap, 1rem)' }">

        <!-- ── 1. Schedule + Storage Card ──────────────────────────────────── -->
        <div class="card rounded-3">
            <div class="card-header d-flex align-items-center justify-content-between">
                <h6 class="my-2">
                    <i class="bi bi-clock-history me-2"></i>
                    <LocaleText t="Scheduled Backups"></LocaleText>
                </h6>
            </div>
            <div class="card-body" :style="{ padding: 'var(--density-card-py, 1rem) var(--density-card-px, 1rem)', fontSize: 'var(--density-font, 0.875rem)' }">

                <!-- Schedule rows -->
                <div class="d-flex flex-column" :style="{ gap: 'var(--density-gap, 0.75rem)' }">

                    <!-- Daily -->
                    <div class="d-flex align-items-center gap-2 ps-2 border-start border-3 border-success rounded-1 flex-wrap">
                        <div class="form-check form-switch mb-0 d-flex align-items-center gap-2" style="min-width:110px">
                            <input class="form-check-input" type="checkbox" v-model="settings.backup_daily_enabled" role="switch" id="dailySwitch">
                            <label class="form-check-label fw-semibold text-success-emphasis" for="dailySwitch">
                                <LocaleText t="Daily"></LocaleText>
                            </label>
                        </div>
                        <div class="d-flex align-items-center gap-1 flex-wrap" :class="{ 'opacity-50': !settings.backup_daily_enabled }">
                            <span class="text-body-secondary"><LocaleText t="At"></LocaleText></span>
                            <input type="time" class="form-control form-control-sm rounded-2" style="width:110px" v-model="settings.backup_daily_time" :disabled="!settings.backup_daily_enabled">
                            <span class="text-body-secondary ms-2"><LocaleText t="Keep"></LocaleText></span>
                            <select class="form-select form-select-sm rounded-2" style="width:80px" v-model.number="settings.backup_daily_keep" :disabled="!settings.backup_daily_enabled">
                                <option v-for="n in [1,3,5,7,10,14,30]" :key="n" :value="n">{{ n }}</option>
                            </select>
                        </div>
                    </div>

                    <!-- Weekly -->
                    <div class="d-flex align-items-center gap-2 ps-2 border-start border-3 border-warning rounded-1 flex-wrap">
                        <div class="form-check form-switch mb-0 d-flex align-items-center gap-2" style="min-width:110px">
                            <input class="form-check-input" type="checkbox" v-model="settings.backup_weekly_enabled" role="switch" id="weeklySwitch">
                            <label class="form-check-label fw-semibold text-warning-emphasis" for="weeklySwitch">
                                <LocaleText t="Weekly"></LocaleText>
                            </label>
                        </div>
                        <div class="d-flex align-items-center gap-1 flex-wrap" :class="{ 'opacity-50': !settings.backup_weekly_enabled }">
                            <span class="text-body-secondary"><LocaleText t="On"></LocaleText></span>
                            <select class="form-select form-select-sm rounded-2" style="width:120px" v-model="settings.backup_weekly_day" :disabled="!settings.backup_weekly_enabled">
                                <option v-for="d in ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']" :key="d" :value="d">{{ d.charAt(0).toUpperCase() + d.slice(1) }}</option>
                            </select>
                            <span class="text-body-secondary"><LocaleText t="at"></LocaleText></span>
                            <input type="time" class="form-control form-control-sm rounded-2" style="width:110px" v-model="settings.backup_weekly_time" :disabled="!settings.backup_weekly_enabled">
                            <span class="text-body-secondary ms-2"><LocaleText t="Keep"></LocaleText></span>
                            <select class="form-select form-select-sm rounded-2" style="width:80px" v-model.number="settings.backup_weekly_keep" :disabled="!settings.backup_weekly_enabled">
                                <option v-for="n in [1,2,4,8,12]" :key="n" :value="n">{{ n }}</option>
                            </select>
                        </div>
                    </div>

                    <!-- Monthly -->
                    <div class="d-flex align-items-center gap-2 ps-2 border-start border-3 border-info rounded-1 flex-wrap">
                        <div class="form-check form-switch mb-0 d-flex align-items-center gap-2" style="min-width:110px">
                            <input class="form-check-input" type="checkbox" v-model="settings.backup_monthly_enabled" role="switch" id="monthlySwitch">
                            <label class="form-check-label fw-semibold text-info-emphasis" for="monthlySwitch">
                                <LocaleText t="Monthly"></LocaleText>
                            </label>
                        </div>
                        <div class="d-flex align-items-center gap-1 flex-wrap" :class="{ 'opacity-50': !settings.backup_monthly_enabled }">
                            <span class="text-body-secondary"><LocaleText t="Day"></LocaleText></span>
                            <input type="number" class="form-control form-control-sm rounded-2" style="width:70px" min="1" max="28" v-model.number="settings.backup_monthly_day" :disabled="!settings.backup_monthly_enabled">
                            <span class="text-body-secondary"><LocaleText t="at"></LocaleText></span>
                            <input type="time" class="form-control form-control-sm rounded-2" style="width:110px" v-model="settings.backup_monthly_time" :disabled="!settings.backup_monthly_enabled">
                            <span class="text-body-secondary ms-2"><LocaleText t="Keep"></LocaleText></span>
                            <select class="form-select form-select-sm rounded-2" style="width:80px" v-model.number="settings.backup_monthly_keep" :disabled="!settings.backup_monthly_enabled">
                                <option v-for="n in [1,2,3,6,12]" :key="n" :value="n">{{ n }}</option>
                            </select>
                        </div>
                    </div>
                </div>

                <!-- Storage bar row -->
                <div class="mt-3 d-flex align-items-center gap-2">
                    <i class="bi bi-hdd text-body-secondary"></i>
                    <div class="flex-grow-1">
                        <div class="progress rounded-2" style="height:8px">
                            <div class="progress-bar" :class="storageBarClass" role="progressbar"
                                 :style="{ width: storagePercent + '%' }"></div>
                        </div>
                    </div>
                    <small class="text-body-secondary text-nowrap">{{ storageUsed }} / {{ storageMax }} MB</small>
                    <button class="btn btn-sm btn-link p-0 text-body-secondary" @click="storageExpanded = !storageExpanded" title="Storage settings">
                        <i class="bi" :class="storageExpanded ? 'bi-chevron-up' : 'bi-gear'"></i>
                    </button>
                </div>

                <!-- Expandable storage settings -->
                <Transition name="fade-slide">
                    <div v-if="storageExpanded" class="mt-3 pt-3 border-top">
                        <div class="row g-2 align-items-end">
                            <div class="col-sm-6">
                                <label class="form-label mb-1" :style="{ fontSize: 'var(--density-font-sm, 0.75rem)' }">
                                    <LocaleText t="Backup Path"></LocaleText>
                                </label>
                                <input type="text" class="form-control form-control-sm rounded-2"
                                       v-model="settings.backup_path"
                                       placeholder="/path/to/backups">
                            </div>
                            <div class="col-sm-3">
                                <label class="form-label mb-1" :style="{ fontSize: 'var(--density-font-sm, 0.75rem)' }">
                                    <LocaleText t="Max Storage (MB)"></LocaleText>
                                </label>
                                <select class="form-select form-select-sm rounded-2" v-model.number="settings.backup_max_size">
                                    <option v-for="n in [256, 512, 1024, 2048, 5120, 10240]" :key="n" :value="n">{{ n >= 1024 ? (n/1024) + ' GB' : n + ' MB' }}</option>
                                </select>
                            </div>
                            <div class="col-sm-3">
                                <label class="form-label mb-1" :style="{ fontSize: 'var(--density-font-sm, 0.75rem)' }">
                                    <LocaleText t="Auto-backup debounce (s)"></LocaleText>
                                </label>
                                <select class="form-select form-select-sm rounded-2" v-model.number="settings.backup_auto_debounce">
                                    <option v-for="n in [5, 15, 30, 60, 120, 300]" :key="n" :value="n">{{ n }}s</option>
                                </select>
                            </div>
                            <div class="col-12 d-flex gap-3">
                                <div class="form-check form-switch mb-0">
                                    <input class="form-check-input" type="checkbox" v-model="settings.backup_auto_on_config_change" role="switch" id="autoConfigSwitch">
                                    <label class="form-check-label" for="autoConfigSwitch" :style="{ fontSize: 'var(--density-font-sm, 0.75rem)' }">
                                        <LocaleText t="Auto-backup on config change"></LocaleText>
                                    </label>
                                </div>
                                <div class="form-check form-switch mb-0">
                                    <input class="form-check-input" type="checkbox" v-model="settings.backup_auto_on_settings_change" role="switch" id="autoSettingsSwitch">
                                    <label class="form-check-label" for="autoSettingsSwitch" :style="{ fontSize: 'var(--density-font-sm, 0.75rem)' }">
                                        <LocaleText t="Auto-backup on settings change"></LocaleText>
                                    </label>
                                </div>
                            </div>
                        </div>
                    </div>
                </Transition>
            </div>
        </div>

        <!-- ── 2. Action Bar ────────────────────────────────────────────────── -->
        <div class="d-flex align-items-center flex-wrap" :style="{ gap: 'var(--density-gap, 0.75rem)' }">
            <button class="btn btn-sm btn-success-subtle rounded-3 border border-success-subtle text-success-emphasis px-3"
                    @click="createSnapshot" :disabled="loading">
                <i class="bi bi-plus-circle me-1"></i>
                <LocaleText t="Create Snapshot"></LocaleText>
                <span v-if="loading" class="spinner-border spinner-border-sm ms-1"></span>
            </button>

            <span class="text-body-secondary" :style="{ fontSize: 'var(--density-font, 0.875rem)' }">
                {{ backups.length }} <LocaleText t="backups"></LocaleText>
            </span>

            <!-- Filter pills -->
            <div class="d-flex gap-1 flex-wrap ms-auto">
                <button v-for="f in ['all','daily','weekly','monthly','auto']" :key="f"
                        class="btn btn-sm rounded-pill"
                        :class="activeFilter === f ? 'btn-primary' : 'btn-outline-secondary'"
                        @click="activeFilter = f"
                        :style="{ fontSize: 'var(--density-font-sm, 0.75rem)' }">
                    {{ f.charAt(0).toUpperCase() + f.slice(1) }}
                </button>
            </div>

            <!-- View toggle -->
            <div class="btn-group btn-group-sm" role="group">
                <button type="button" class="btn rounded-start-3"
                        :class="viewMode === 'table' ? 'btn-primary' : 'btn-outline-secondary'"
                        @click="viewMode = 'table'" title="Table view">
                    <i class="bi bi-table"></i>
                </button>
                <button type="button" class="btn rounded-end-3"
                        :class="viewMode === 'calendar' ? 'btn-primary' : 'btn-outline-secondary'"
                        @click="viewMode = 'calendar'" title="Calendar view">
                    <i class="bi bi-calendar3"></i>
                </button>
            </div>
        </div>

        <!-- ── 3. Table View ────────────────────────────────────────────────── -->
        <Transition name="fade" mode="out-in">
            <div v-if="viewMode === 'table'" key="table" class="card rounded-3">
                <div class="card-body p-0">
                    <div v-if="backupsLoading" class="text-center py-4 text-body-secondary">
                        <span class="spinner-border spinner-border-sm me-2"></span>
                        <LocaleText t="Loading backups..."></LocaleText>
                    </div>
                    <div v-else-if="filteredBackups.length === 0" class="text-center py-5 text-body-secondary">
                        <i class="bi bi-inbox fs-2 d-block mb-2"></i>
                        <LocaleText t="No backups found"></LocaleText>
                    </div>
                    <div v-else class="table-responsive">
                        <table class="table table-sm table-striped mb-0 align-middle" :style="{ fontSize: 'var(--density-font, 0.875rem)' }">
                            <thead>
                                <tr>
                                    <th class="ps-3"><LocaleText t="Name"></LocaleText></th>
                                    <th><LocaleText t="Date"></LocaleText></th>
                                    <th><LocaleText t="Type"></LocaleText></th>
                                    <th><LocaleText t="Size"></LocaleText></th>
                                    <th class="pe-3 text-end"><LocaleText t="Actions"></LocaleText></th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-for="b in filteredBackups" :key="b.name">
                                    <td class="ps-3">
                                        <samp style="font-size: 0.8em">{{ b.name }}</samp>
                                    </td>
                                    <td class="text-body-secondary">{{ formatDate(b.date) }}</td>
                                    <td>
                                        <span class="badge rounded-pill border" :class="typeBadgeClass(b.type)" :style="{ fontSize: 'var(--density-font-sm, 0.7rem)' }">
                                            {{ b.type || 'manual' }}
                                        </span>
                                    </td>
                                    <td class="text-body-secondary">{{ formatSize(b.size) }}</td>
                                    <td class="pe-3 text-end">
                                        <div class="btn-group btn-group-sm">
                                            <button class="btn btn-outline-secondary rounded-start-2" title="Download" @click="downloadBackup(b.name)">
                                                <i class="bi bi-download"></i>
                                            </button>
                                            <button class="btn btn-outline-primary" title="Restore" @click="openRestoreModal(b)">
                                                <i class="bi bi-arrow-counterclockwise"></i>
                                            </button>
                                            <button class="btn btn-outline-danger rounded-end-2" title="Delete" @click="deleteBackup(b.name)">
                                                <i class="bi bi-trash3"></i>
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- ── 4. Calendar View ───────────────────────────────────────── -->
            <div v-else key="calendar" class="row g-3">
                <!-- Left: calendar -->
                <div class="col-md-8">
                    <div class="card rounded-3">
                        <div class="card-header d-flex align-items-center justify-content-between">
                            <button class="btn btn-sm btn-link p-0 text-body" @click="prevMonth">
                                <i class="bi bi-chevron-left"></i>
                            </button>
                            <h6 class="mb-0">{{ calendarDate.format("MMMM YYYY") }}</h6>
                            <button class="btn btn-sm btn-link p-0 text-body" @click="nextMonth">
                                <i class="bi bi-chevron-right"></i>
                            </button>
                        </div>
                        <div class="card-body" :style="{ padding: 'var(--density-card-py, 0.75rem) var(--density-card-px, 0.75rem)' }">
                            <!-- Week day headers -->
                            <div class="row g-1 mb-1">
                                <div v-for="wd in weekDays" :key="wd" class="col text-center">
                                    <small class="text-body-secondary fw-semibold" :style="{ fontSize: 'var(--density-font-sm, 0.7rem)' }">{{ wd }}</small>
                                </div>
                            </div>
                            <!-- Calendar grid -->
                            <div class="row g-1">
                                <div v-for="(day, idx) in calendarDays" :key="idx" class="col">
                                    <div v-if="day"
                                         class="rounded-2 text-center position-relative"
                                         style="min-height:48px; cursor:pointer"
                                         :class="[
                                             selectedDay && selectedDay.isSame(day, 'day') ? 'bg-primary text-white' : 'hover-bg',
                                             backupsByDay[day.format('YYYY-MM-DD')]?.length ? '' : ''
                                         ]"
                                         @click="calendarDayClick(day)">
                                        <div class="py-1" :style="{ fontSize: 'var(--density-font-sm, 0.75rem)' }">{{ day.date() }}</div>
                                        <!-- Dots -->
                                        <div class="d-flex justify-content-center gap-1 pb-1 flex-wrap">
                                            <span v-for="b in (backupsByDay[day.format('YYYY-MM-DD')] || []).slice(0,4)"
                                                  :key="b.name"
                                                  class="rounded-circle d-inline-block"
                                                  :class="dotClass(b.type)"
                                                  style="width:6px;height:6px"></span>
                                        </div>
                                    </div>
                                    <div v-else style="min-height:48px"></div>
                                </div>
                            </div>

                            <!-- Selected day detail -->
                            <Transition name="fade-slide">
                                <div v-if="selectedDay && selectedDayBackups.length" class="mt-3 pt-3 border-top">
                                    <h6 :style="{ fontSize: 'var(--density-font, 0.875rem)' }">
                                        {{ selectedDay.format("MMMM D, YYYY") }}
                                        <span class="badge bg-secondary-subtle text-secondary-emphasis border border-secondary-subtle ms-1 rounded-pill">{{ selectedDayBackups.length }}</span>
                                    </h6>
                                    <div class="d-flex flex-column" :style="{ gap: 'var(--density-gap, 0.5rem)' }">
                                        <div v-for="b in selectedDayBackups" :key="b.name"
                                             class="d-flex align-items-center gap-2 p-2 rounded-2 bg-body-secondary">
                                            <span class="badge rounded-pill border" :class="typeBadgeClass(b.type)" :style="{ fontSize: 'var(--density-font-sm, 0.7rem)' }">
                                                {{ b.type || 'manual' }}
                                            </span>
                                            <samp style="font-size:0.8em; flex:1" class="text-truncate">{{ b.name }}</samp>
                                            <span class="text-body-secondary" :style="{ fontSize: 'var(--density-font-sm, 0.75rem)' }">{{ formatSize(b.size) }}</span>
                                            <div class="btn-group btn-group-sm">
                                                <button class="btn btn-outline-secondary btn-sm rounded-start-2" @click="downloadBackup(b.name)"><i class="bi bi-download"></i></button>
                                                <button class="btn btn-outline-primary btn-sm" @click="openRestoreModal(b)"><i class="bi bi-arrow-counterclockwise"></i></button>
                                                <button class="btn btn-outline-danger btn-sm rounded-end-2" @click="deleteBackup(b.name)"><i class="bi bi-trash3"></i></button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div v-else-if="selectedDay" class="mt-3 pt-3 border-top text-center text-body-secondary py-2">
                                    <LocaleText t="No backups on this day"></LocaleText>
                                </div>
                            </Transition>
                        </div>
                    </div>
                </div>

                <!-- Right: stats -->
                <div class="col-md-4">
                    <div class="card rounded-3">
                        <div class="card-header">
                            <h6 class="my-2">
                                <i class="bi bi-bar-chart-line me-2"></i>
                                <LocaleText t="Statistics"></LocaleText>
                            </h6>
                        </div>
                        <div class="card-body" :style="{ fontSize: 'var(--density-font, 0.875rem)', padding: 'var(--density-card-py, 1rem) var(--density-card-px, 1rem)' }">
                            <div class="d-flex flex-column" :style="{ gap: 'var(--density-gap, 0.5rem)' }">
                                <div class="d-flex justify-content-between">
                                    <span class="text-body-secondary"><LocaleText t="Total Backups"></LocaleText></span>
                                    <strong>{{ backups.length }}</strong>
                                </div>
                                <div class="d-flex justify-content-between">
                                    <span class="d-flex align-items-center gap-1">
                                        <span class="rounded-circle bg-success d-inline-block" style="width:8px;height:8px"></span>
                                        <LocaleText t="Daily"></LocaleText>
                                    </span>
                                    <strong>{{ backupCountByType.daily }}</strong>
                                </div>
                                <div class="d-flex justify-content-between">
                                    <span class="d-flex align-items-center gap-1">
                                        <span class="rounded-circle bg-warning d-inline-block" style="width:8px;height:8px"></span>
                                        <LocaleText t="Weekly"></LocaleText>
                                    </span>
                                    <strong>{{ backupCountByType.weekly }}</strong>
                                </div>
                                <div class="d-flex justify-content-between">
                                    <span class="d-flex align-items-center gap-1">
                                        <span class="rounded-circle bg-info d-inline-block" style="width:8px;height:8px"></span>
                                        <LocaleText t="Monthly"></LocaleText>
                                    </span>
                                    <strong>{{ backupCountByType.monthly }}</strong>
                                </div>
                                <div class="d-flex justify-content-between">
                                    <span class="d-flex align-items-center gap-1">
                                        <span class="rounded-circle bg-secondary d-inline-block" style="width:8px;height:8px"></span>
                                        <LocaleText t="Manual / Auto"></LocaleText>
                                    </span>
                                    <strong>{{ backupCountByType.manual + backupCountByType.auto }}</strong>
                                </div>
                                <hr class="my-1">
                                <div class="d-flex justify-content-between">
                                    <span class="text-body-secondary"><LocaleText t="Last Backup"></LocaleText></span>
                                    <span>{{ lastBackup ? formatDate(lastBackup.date) : '—' }}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </Transition>

        <!-- ── 5. Restore Modal ─────────────────────────────────────────────── -->
        <Transition name="modal">
            <div v-if="restoreModal" class="modal d-block" tabindex="-1" @click.self="closeRestoreModal" style="background:rgba(0,0,0,0.5)">
                <div class="modal-dialog modal-dialog-centered modal-dialog-scrollable">
                    <div class="modal-content rounded-3">
                        <div class="modal-header border-bottom">
                            <h5 class="modal-title">
                                <i class="bi bi-arrow-counterclockwise me-2 text-primary"></i>
                                <LocaleText t="Restore Backup"></LocaleText>
                            </h5>
                            <button type="button" class="btn-close" @click="closeRestoreModal"></button>
                        </div>
                        <div class="modal-body" :style="{ fontSize: 'var(--density-font, 0.875rem)' }">
                            <div v-if="restoreTarget" class="mb-3">
                                <div class="bg-body-secondary rounded-2 p-2">
                                    <samp style="font-size:0.8em">{{ restoreTarget.name }}</samp>
                                    <span class="ms-2 badge rounded-pill border" :class="typeBadgeClass(restoreTarget.type)">{{ restoreTarget.type || 'manual' }}</span>
                                </div>
                            </div>

                            <!-- Select all -->
                            <div class="form-check mb-2">
                                <input class="form-check-input" type="checkbox" id="selectAllRestore"
                                       :checked="allRestoreSelected"
                                       :indeterminate.prop="!allRestoreSelected && restoreSelectedCount > 0"
                                       @change="toggleAllRestore">
                                <label class="form-check-label fw-semibold" for="selectAllRestore">
                                    <LocaleText t="Select All"></LocaleText>
                                </label>
                            </div>
                            <div class="border rounded-2 p-2 d-flex flex-column" :style="{ gap: '0.4rem' }">
                                <div class="form-check mb-0">
                                    <input class="form-check-input" type="checkbox" id="rc_wg" v-model="restoreComponents.wireguard_configurations">
                                    <label class="form-check-label" for="rc_wg">
                                        <i class="bi bi-diagram-3 me-1 text-body-secondary"></i>
                                        <LocaleText t="WireGuard Configurations"></LocaleText>
                                    </label>
                                </div>
                                <div class="form-check mb-0">
                                    <input class="form-check-input" type="checkbox" id="rc_dash" v-model="restoreComponents.dashboard_settings">
                                    <label class="form-check-label" for="rc_dash">
                                        <i class="bi bi-gear me-1 text-body-secondary"></i>
                                        <LocaleText t="Dashboard Settings"></LocaleText>
                                    </label>
                                </div>
                                <div class="form-check mb-0">
                                    <input class="form-check-input" type="checkbox" id="rc_hooks" v-model="restoreComponents.webhooks">
                                    <label class="form-check-label" for="rc_hooks">
                                        <i class="bi bi-broadcast me-1 text-body-secondary"></i>
                                        <LocaleText t="Webhooks"></LocaleText>
                                    </label>
                                </div>
                                <div class="form-check mb-0">
                                    <input class="form-check-input" type="checkbox" id="rc_jobs" v-model="restoreComponents.peer_jobs">
                                    <label class="form-check-label" for="rc_jobs">
                                        <i class="bi bi-clock me-1 text-body-secondary"></i>
                                        <LocaleText t="Peer Jobs"></LocaleText>
                                    </label>
                                </div>
                                <div class="form-check mb-0">
                                    <input class="form-check-input" type="checkbox" id="rc_share" v-model="restoreComponents.share_links">
                                    <label class="form-check-label" for="rc_share">
                                        <i class="bi bi-share me-1 text-body-secondary"></i>
                                        <LocaleText t="Share Links"></LocaleText>
                                    </label>
                                </div>
                                <div class="form-check mb-0">
                                    <input class="form-check-input" type="checkbox" id="rc_portal" v-model="restoreComponents.client_portal">
                                    <label class="form-check-label" for="rc_portal">
                                        <i class="bi bi-person-badge me-1 text-body-secondary"></i>
                                        <LocaleText t="Client Portal"></LocaleText>
                                    </label>
                                </div>
                                <div class="form-check mb-0">
                                    <input class="form-check-input" type="checkbox" id="rc_apikeys" v-model="restoreComponents.api_keys">
                                    <label class="form-check-label" for="rc_apikeys">
                                        <i class="bi bi-key me-1 text-body-secondary"></i>
                                        <LocaleText t="API Keys"></LocaleText>
                                    </label>
                                </div>
                            </div>

                            <div class="alert alert-warning rounded-3 mt-3 mb-0 d-flex gap-2 align-items-start" :style="{ fontSize: 'var(--density-font-sm, 0.8rem)' }">
                                <i class="bi bi-exclamation-triangle-fill flex-shrink-0 mt-1"></i>
                                <span><LocaleText t="Restoring WireGuard Configurations may disconnect active peers. Proceed with caution."></LocaleText></span>
                            </div>
                        </div>
                        <div class="modal-footer border-top">
                            <button type="button" class="btn btn-sm btn-outline-secondary rounded-3" @click="closeRestoreModal">
                                <LocaleText t="Cancel"></LocaleText>
                            </button>
                            <button type="button" class="btn btn-sm btn-primary rounded-3" @click="doRestore" :disabled="restoreSelectedCount === 0">
                                <i class="bi bi-arrow-counterclockwise me-1"></i>
                                <LocaleText t="Restore Selected"></LocaleText>
                                ({{ restoreSelectedCount }})
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </Transition>

    </div>
</template>

<style scoped>
.fade-slide-enter-active,
.fade-slide-leave-active {
    transition: opacity 0.2s ease, transform 0.2s ease;
}
.fade-slide-enter-from,
.fade-slide-leave-to {
    opacity: 0;
    transform: translateY(-6px);
}

.fade-enter-active,
.fade-leave-active {
    transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
    opacity: 0;
}

.modal-enter-active,
.modal-leave-active {
    transition: opacity 0.2s ease;
}
.modal-enter-from,
.modal-leave-to {
    opacity: 0;
}

.hover-bg:hover {
    background-color: var(--bs-secondary-bg);
}
</style>
