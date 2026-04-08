<template>
  <div class="neon-terminal" :class="{ 'neon-terminal--single': mode === 'single' }">
    <template v-if="mode === 'single'">
      <div class="neon-info-bar">
        <div class="neon-info-item">
          <span class="neon-label">ADDRESS</span>
          <span class="neon-cyan">{{ interfaceData?.address || '—' }}</span>
        </div>
        <div class="neon-info-item">
          <span class="neon-label">PORT</span>
          <span class="neon-text">{{ interfaceData?.listenPort || '—' }}</span>
        </div>
        <div class="neon-info-item">
          <span class="neon-label">PEERS</span>
          <span class="neon-green">{{ onlinePeers }}</span>
          <span class="neon-muted"> / {{ totalPeers }}</span>
        </div>
        <div class="neon-info-item">
          <span class="neon-label">TRAFFIC</span>
          <span class="neon-cyan">↓ {{ formatBytes(totalRx) }}</span>&nbsp;&nbsp;
          <span class="neon-orange">↑ {{ formatBytes(totalTx) }}</span>
        </div>
        <div class="neon-info-item ms-auto">
          <span class="neon-label">PUBLIC KEY</span>
          <span class="neon-muted neon-small" role="button" @click="copyKey">
            {{ truncateKey(interfaceData?.publicKey) }} <span class="neon-purple">⧉</span>
          </span>
        </div>
      </div>
    </template>

    <template v-for="(iface, ifaceName) in allInterfaces" :key="ifaceName">
      <div class="neon-body">
        <div v-if="mode === 'all'" class="neon-section-header neon-purple">
          ── {{ ifaceName }} ──
        </div>

        <!-- Interface -->
        <div class="neon-section">
          <div class="neon-section-header neon-purple">── Interface ──</div>
          <div class="neon-row-inline">
            <span class="neon-muted">state:</span>
            <span :class="iface.status === 'up' ? 'neon-green pulse-green' : 'neon-red pulse-red'">●</span>
            <span :class="iface.status === 'up' ? 'neon-green' : 'neon-red'">{{ iface.status?.toUpperCase() }}</span>
            &nbsp;&nbsp;&nbsp;
            <span class="neon-muted">mtu:</span>
            <span class="neon-text">{{ iface.mtu || '—' }}</span>
            &nbsp;&nbsp;&nbsp;
            <template v-if="iface.fwmark">
              <span class="neon-muted">fwmark:</span>
              <span class="neon-text">{{ iface.fwmark }}</span>
            </template>
          </div>
        </div>

        <!-- Peers -->
        <div class="neon-section" v-if="iface.peers?.length">
          <div class="neon-section-header neon-purple">── Peers ──</div>
          <table class="neon-table">
            <thead>
              <tr class="neon-muted">
                <td>PEER</td><td>ENDPOINT</td><td>ALLOWED IPS</td>
                <td>HANDSHAKE</td><td>TRANSFER</td><td>STATUS</td>
              </tr>
            </thead>
            <tbody>
              <tr v-for="peer in iface.peers" :key="peer.publicKey" class="neon-table-row">
                <td class="neon-text">{{ peer.name }}</td>
                <td :class="peer.endpoint ? 'neon-text' : 'neon-muted'">{{ peer.endpoint || '(none)' }}</td>
                <td class="neon-text">{{ peer.allowedIps?.join(', ') }}</td>
                <td :class="handshakeClass(peer)">{{ peer.latestHandshake || 'never' }}</td>
                <td>
                  <template v-if="peer.transferRx || peer.transferTx">
                    <span class="neon-cyan">↓{{ formatBytes(peer.transferRx) }}</span>
                    <span class="neon-orange"> ↑{{ formatBytes(peer.transferTx) }}</span>
                  </template>
                  <span v-else class="neon-muted">—</span>
                </td>
                <td>
                  <span :class="statusIndicatorClass(peer.status)">●</span>
                  <span :class="statusTextClass(peer.status)">{{ peer.status }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Routes -->
        <div class="neon-section" v-if="iface.routes?.length">
          <div class="neon-section-header neon-purple">
            ── System Routes (via {{ ifaceName }}) ──
          </div>
          <table class="neon-table">
            <thead>
              <tr class="neon-muted">
                <td>DESTINATION</td><td>GATEWAY</td><td>METRIC</td><td>PEER</td><td>STATUS</td>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(route, idx) in iface.routes" :key="idx" class="neon-table-row">
                <td class="neon-cyan">{{ route.destination }}</td>
                <td class="neon-text">{{ route.gateway }}</td>
                <td class="neon-text">{{ route.metric }}</td>
                <td :class="route.peer ? 'neon-text' : 'neon-muted'">{{ route.peer || '—' }}</td>
                <td>
                  <template v-if="route.status === 'ok'">
                    <span class="neon-green">✓ {{ route.statusText }}</span>
                  </template>
                  <template v-else>
                    <span class="neon-orange pulse-orange">⚠</span>
                    <span class="neon-orange"> {{ route.statusText }}</span>
                  </template>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Warnings -->
        <div class="neon-section" v-if="iface.warnings?.length">
          <div class="neon-section-header neon-red">── Warnings ──</div>
          <div v-for="(w, idx) in iface.warnings" :key="idx" class="neon-warning-row">
            <span class="neon-orange pulse-orange">⚠</span>
            <span class="neon-text">{{ w.target }}</span>
            <span class="neon-muted"> — {{ w.message }}</span>
          </div>
        </div>
      </div>
    </template>

    <!-- Footer -->
    <div class="neon-footer">
      <span class="neon-muted">
        <span :class="connected ? 'neon-green pulse-green' : 'neon-red pulse-red'">●</span>
        {{ connected ? 'SSE connected — live updates' : 'SSE disconnected — reconnecting...' }}
      </span>
      <span class="neon-muted">Last event: {{ lastEventTime }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { getUrl } from '@/utilities/fetch.js';
import { DashboardConfigurationStore } from '@/stores/DashboardConfigurationStore.js';

const props = defineProps({
  mode: { type: String, default: 'all' },
  interface: { type: String, default: null },
});

const interfaces = ref({});
const connected = ref(false);
const lastEventTime = ref('—');
let eventSource = null;

const allInterfaces = computed(() => interfaces.value);

const interfaceData = computed(() => {
  if (props.mode === 'single' && props.interface) {
    return interfaces.value[props.interface] || null;
  }
  return null;
});

const onlinePeers = computed(() => {
  const iface = interfaceData.value;
  if (!iface?.peers) return 0;
  return iface.peers.filter(p => p.status === 'online').length;
});

const totalPeers = computed(() => {
  const iface = interfaceData.value;
  return iface?.peers?.length || 0;
});

const totalRx = computed(() => {
  const iface = interfaceData.value;
  if (!iface?.peers) return 0;
  return iface.peers.reduce((sum, p) => sum + (p.transferRx || 0), 0);
});

const totalTx = computed(() => {
  const iface = interfaceData.value;
  if (!iface?.peers) return 0;
  return iface.peers.reduce((sum, p) => sum + (p.transferTx || 0), 0);
});

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const units = ['B', 'K', 'M', 'G', 'T'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const val = (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0);
  return `${val}${units[i]}`;
}

function truncateKey(key) {
  if (!key) return '—';
  return key.slice(0, 8) + '…' + key.slice(-4);
}

function copyKey() {
  const key = interfaceData.value?.publicKey;
  if (key) navigator.clipboard.writeText(key);
}

function handshakeClass(peer) {
  if (peer.status === 'online') return 'neon-green';
  if (peer.status === 'offline') return 'neon-red';
  return 'neon-muted';
}

function statusIndicatorClass(status) {
  if (status === 'online') return 'neon-green pulse-green';
  if (status === 'offline') return 'neon-red pulse-red';
  return 'neon-muted';
}

function statusTextClass(status) {
  if (status === 'online') return 'neon-green';
  if (status === 'offline') return 'neon-red';
  return 'neon-muted';
}

function connectSSE() {
  const searchParams = new URLSearchParams();
  if (props.mode === 'single' && props.interface) {
    searchParams.set('interface', props.interface);
  }
  // For cross-server mode, pass API key as query param since EventSource can't set headers
  const store = DashboardConfigurationStore();
  const crossServer = store.getActiveCrossServer();
  if (crossServer) {
    searchParams.set('apikey', crossServer.apiKey);
  }
  const paramStr = searchParams.toString();
  const url = getUrl(`/api/sse/diagnostics${paramStr ? '?' + paramStr : ''}`);

  eventSource = new EventSource(url);

  eventSource.onopen = () => {
    connected.value = true;
  };

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.interfaces) {
      for (const [name, snap] of Object.entries(data.interfaces)) {
        interfaces.value[name] = snap;
      }
    }
    const now = new Date();
    lastEventTime.value = now.toLocaleTimeString();
  };

  eventSource.onerror = () => {
    connected.value = false;
  };
}

onMounted(() => {
  connectSSE();
});

onBeforeUnmount(() => {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
});
</script>

<style scoped>
@keyframes pulse-green-anim {
  0%, 100% { opacity: 1; text-shadow: 0 0 4px #50fa7b, 0 0 8px rgba(80,250,123,0.27); }
  50% { opacity: 0.6; text-shadow: 0 0 2px rgba(80,250,123,0.4); }
}
@keyframes pulse-red-anim {
  0%, 100% { opacity: 1; text-shadow: 0 0 4px #ff5555, 0 0 8px rgba(255,85,85,0.27); }
  50% { opacity: 0.6; text-shadow: 0 0 2px rgba(255,85,85,0.4); }
}
@keyframes pulse-orange-anim {
  0%, 100% { opacity: 1; text-shadow: 0 0 4px #ffb86c, 0 0 8px rgba(255,184,108,0.27); }
  50% { opacity: 0.6; text-shadow: 0 0 2px rgba(255,184,108,0.4); }
}

.neon-terminal {
  background: rgba(30, 30, 35, 0.85);
  backdrop-filter: blur(8px);
  border-radius: 8px;
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 13px;
  overflow: hidden;
}

.neon-info-bar {
  display: flex;
  gap: 24px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.03);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  align-items: center;
  flex-wrap: wrap;
}

.neon-info-item { display: flex; flex-direction: column; }
.neon-label { color: #6b7394; font-size: 11px; text-shadow: 0 0 1px rgba(107,115,148,0.07); }
.neon-small { font-size: 11px; }

.neon-body { padding: 16px; line-height: 1.8; }

.neon-section { padding-bottom: 12px; margin-top: 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); }
.neon-section:last-of-type { border-bottom: none; }
.neon-section-header { font-weight: bold; margin-bottom: 6px; }
.neon-row-inline { padding-left: 8px; }

.neon-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.neon-table td { padding: 4px 12px; }
.neon-table thead td { padding: 4px 12px 6px; }
.neon-table-row:hover { background: rgba(255, 255, 255, 0.03); }

.neon-warning-row { padding-left: 8px; line-height: 2; }

.neon-footer {
  margin: 0 16px;
  padding: 10px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  justify-content: space-between;
  font-size: 11px;
}

/* Neon colors */
.neon-green { color: #50fa7b; text-shadow: 0 0 4px rgba(80,250,123,0.4), 0 0 10px rgba(80,250,123,0.13); }
.neon-red { color: #ff5555; text-shadow: 0 0 4px rgba(255,85,85,0.4), 0 0 10px rgba(255,85,85,0.13); }
.neon-cyan { color: #8be9fd; text-shadow: 0 0 4px rgba(139,233,253,0.27), 0 0 8px rgba(139,233,253,0.13); }
.neon-orange { color: #ffb86c; text-shadow: 0 0 4px rgba(255,184,108,0.27), 0 0 8px rgba(255,184,108,0.13); }
.neon-purple { color: #bd93f9; text-shadow: 0 0 4px rgba(189,147,249,0.4), 0 0 10px rgba(189,147,249,0.13); }
.neon-text { color: #e2e8f0; text-shadow: 0 0 2px rgba(226,232,240,0.13); }
.neon-muted { color: #6b7394; text-shadow: 0 0 1px rgba(107,115,148,0.07); }

/* Pulse animations */
.pulse-green { animation: pulse-green-anim 2s ease-in-out infinite; }
.pulse-red { animation: pulse-red-anim 1.5s ease-in-out infinite; }
.pulse-orange { animation: pulse-orange-anim 1.8s ease-in-out infinite; }
</style>
