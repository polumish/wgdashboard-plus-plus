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
          <div class="neon-row-inline" v-if="iface.counters">
            <span class="neon-muted">rx:</span>
            <span class="neon-text">{{ iface.counters.rx_packets?.toLocaleString() || 0 }}</span>
            <span class="neon-muted">pkt</span>
            &nbsp;&nbsp;
            <span class="neon-muted">tx:</span>
            <span class="neon-text">{{ iface.counters.tx_packets?.toLocaleString() || 0 }}</span>
            <span class="neon-muted">pkt</span>
            &nbsp;&nbsp;&nbsp;
            <span class="neon-muted">err rx/tx:</span>
            <span :class="(iface.counters.rx_errors || iface.counters.tx_errors) ? 'neon-orange' : 'neon-green'">
              {{ iface.counters.rx_errors || 0 }} / {{ iface.counters.tx_errors || 0 }}
            </span>
            &nbsp;&nbsp;
            <span class="neon-muted">drop rx/tx:</span>
            <span :class="(iface.counters.rx_dropped || iface.counters.tx_dropped) ? 'neon-orange' : 'neon-green'">
              {{ iface.counters.rx_dropped || 0 }} / {{ iface.counters.tx_dropped || 0 }}
            </span>
          </div>
        </div>

        <!-- Peers -->
        <div class="neon-section" v-if="iface.peers?.length">
          <div class="neon-section-header neon-purple">── Peers ──</div>
          <table class="neon-table neon-table-peers">
            <colgroup>
              <col style="width: 14%;">   <!-- PEER -->
              <col style="width: 18%;">   <!-- ENDPOINT -->
              <col style="width: 18%;">   <!-- ALLOWED IPS -->
              <col style="width: 14%;">   <!-- HANDSHAKE -->
              <col style="width: 14%;">   <!-- TRANSFER -->
              <col style="width: 12%;">   <!-- PMTU -->
              <col style="width: 10%;">   <!-- STATUS -->
            </colgroup>
            <thead>
              <tr class="neon-muted">
                <td>PEER</td><td>ENDPOINT</td><td>ALLOWED IPS</td>
                <td>HANDSHAKE</td><td>TRANSFER</td><td>PMTU</td><td>STATUS</td>
              </tr>
            </thead>
            <tbody>
              <tr v-for="peer in iface.peers" :key="peer.publicKey" class="neon-table-row">
                <td class="neon-text" :title="peer.name">{{ peer.name }}</td>
                <td :class="peer.endpoint ? 'neon-text' : 'neon-muted'" :title="peer.endpoint || '(none)'">{{ peer.endpoint || '(none)' }}</td>
                <td class="neon-text" :title="peer.allowedIps?.join(', ')">{{ peer.allowedIps?.join(', ') }}</td>
                <td :class="handshakeClass(peer)" :title="peer.latestHandshake || 'never'">{{ peer.latestHandshake || 'never' }}</td>
                <td>
                  <template v-if="peer.transferRx || peer.transferTx">
                    <span class="neon-cyan">↓{{ formatBytes(peer.transferRx) }}</span>
                    <span class="neon-orange"> ↑{{ formatBytes(peer.transferTx) }}</span>
                  </template>
                  <span v-else class="neon-muted">—</span>
                </td>
                <td :class="pmtuClass(peer, iface.mtu)" :title="pmtuTooltip(peer, iface.mtu)">
                  <template v-if="pmtuProbing[peer.publicKey]">
                    <span class="neon-muted">probing…</span>
                  </template>
                  <template v-else-if="peer.pmtu !== null && peer.pmtu !== undefined">
                    <span class="neon-muted">{{ iface.mtu || '?' }} / </span>{{ peer.pmtu }}
                  </template>
                  <span v-else class="neon-muted">—</span>
                  <a role="button"
                     class="neon-muted ms-1"
                     style="text-decoration: none; cursor: pointer;"
                     :title="`Re-probe path MTU for ${peer.name}`"
                     @click.stop="refreshPmtu(ifaceName, peer)"
                     v-if="!pmtuProbing[peer.publicKey]">↻</a>
                </td>
                <td>
                  <span :class="statusIndicatorClass(peer.status)">●</span>
                  <span :class="statusTextClass(peer.status)">{{ peer.status }}</span>
                  <a role="button"
                     class="neon-muted ms-2"
                     style="text-decoration: none; cursor: pointer;"
                     :title="`Run mtr trace to ${peer.endpoint || peer.name}`"
                     @click.stop="runMtr(peer)"
                     v-if="peer.endpoint">⁂</a>
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

    <!-- MTR Modal -->
    <div v-if="mtrModal.open" class="mtr-modal-backdrop" @click.self="closeMtrModal">
      <div class="mtr-modal">
        <div class="mtr-modal-header">
          <span class="neon-purple">── mtr trace ── {{ mtrModal.target }}</span>
          <button class="mtr-close" @click="closeMtrModal">×</button>
        </div>
        <div class="mtr-modal-body">
          <div v-if="mtrModal.loading" class="neon-muted">
            Running mtr (up to 60 seconds)…
          </div>
          <div v-else-if="mtrModal.error" class="neon-red">
            Error: {{ mtrModal.error }}
          </div>
          <pre v-else class="mtr-output">{{ mtrModal.output }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, reactive } from 'vue';
import { getUrl, fetchPost } from '@/utilities/fetch.js';
import { DashboardConfigurationStore } from '@/stores/DashboardConfigurationStore.js';

const props = defineProps({
  mode: { type: String, default: 'all' },
  interface: { type: String, default: null },
});

const interfaces = ref({});
const connected = ref(false);
const lastEventTime = ref('—');
const pmtuProbing = reactive({}); // publicKey → bool
const mtrModal = reactive({
  open: false,
  target: '',
  loading: false,
  output: '',
  error: '',
});
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

// WireGuard overhead: 20 (IPv4) + 8 (UDP) + 32 (WG header) + 16 (auth tag) ≈ 80 bytes.
// To avoid fragmentation: interface MTU + WG_OVERHEAD ≤ detected path MTU.
const WG_OVERHEAD = 80;

function pmtuClass(peer, ifaceMtu) {
  if (peer.pmtu === null || peer.pmtu === undefined) return 'neon-muted';
  if (!ifaceMtu) return 'neon-text';
  const required = ifaceMtu + WG_OVERHEAD;
  if (peer.pmtu < required) return 'neon-orange';   // fragmentation risk
  if (peer.pmtu === required) return 'neon-text';   // exact fit
  return 'neon-green';                              // headroom
}

function pmtuTooltip(peer, ifaceMtu) {
  if (peer.pmtu === null || peer.pmtu === undefined) {
    return 'Path MTU unknown — no recent data or discovery blocked';
  }
  const src = peer.pmtuSource || 'unknown';
  if (!ifaceMtu) {
    return `Detected path MTU: ${peer.pmtu}. Source: ${src}`;
  }
  const required = ifaceMtu + WG_OVERHEAD;
  const headroom = peer.pmtu - required;
  if (peer.pmtu < required) {
    return `Path MTU ${peer.pmtu} is below required ${required} (interface MTU ${ifaceMtu} + ${WG_OVERHEAD} WG overhead). Fragmentation possible. Source: ${src}`;
  }
  return `Interface MTU ${ifaceMtu} + ${WG_OVERHEAD} WG overhead = ${required}. Detected path MTU: ${peer.pmtu}. Headroom: ${headroom} bytes. Source: ${src}`;
}

async function refreshPmtu(ifaceName, peer) {
  const key = peer.publicKey;
  pmtuProbing[key] = true;
  try {
    const store = DashboardConfigurationStore();
    await fetchPost('/api/pmtu/probe', {
      interface: ifaceName,
      publicKey: key,
    }, (res) => {
      if (res.status && res.data) {
        // Update in-memory peer directly so the UI reflects the fresh value
        // even before the next SSE snapshot arrives.
        peer.pmtu = res.data.pmtu;
        peer.pmtuSource = res.data.source;
      } else {
        // Surface failures to the user — previously swallowed silently.
        store.newMessage?.('Server', `PMTU probe failed: ${res.message || 'unknown error'}`, 'danger');
      }
    });
  } catch (e) {
    const store = DashboardConfigurationStore();
    store.newMessage?.('Server', `PMTU probe error: ${e}`, 'danger');
  } finally {
    // Delete the key entirely so the reactive object doesn't accumulate
    // stale entries for peers that get removed over time.
    delete pmtuProbing[key];
  }
}

async function runMtr(peer) {
  // Strip port from endpoint for mtr target
  const target = (peer.endpoint || '').replace(/:\d+$/, '').replace(/^\[|\]$/g, '');
  if (!target) return;
  mtrModal.open = true;
  mtrModal.target = target;
  mtrModal.loading = true;
  mtrModal.output = '';
  mtrModal.error = '';
  try {
    await fetchPost('/api/diagnostics/mtr', { target, cycles: 10 }, (res) => {
      if (res.status && res.data) {
        mtrModal.output = res.data.output;
      } else {
        mtrModal.error = res.message || 'Unknown error';
      }
    });
  } catch (e) {
    mtrModal.error = String(e);
  } finally {
    mtrModal.loading = false;
  }
}

function closeMtrModal() {
  mtrModal.open = false;
  mtrModal.output = '';
  mtrModal.error = '';
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
  // Clear any per-peer probing state and close the MTR modal so nothing
  // persists on a keep-alive remount.
  Object.keys(pmtuProbing).forEach(k => delete pmtuProbing[k]);
  mtrModal.open = false;
  mtrModal.output = '';
  mtrModal.error = '';
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

/* Peers table: fixed layout so columns don't jump when handshake text changes.
   Long values (endpoints, allowed IPs, public keys) are truncated with ellipsis
   and exposed via the title attribute / hover tooltip. */
.neon-table-peers { table-layout: fixed; }
.neon-table-peers td {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

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

/* MTR Modal */
.mtr-modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}
.mtr-modal {
  background: #0b0e1a;
  border: 1px solid rgba(189, 147, 249, 0.4);
  border-radius: 6px;
  box-shadow: 0 0 40px rgba(189, 147, 249, 0.25);
  max-width: 900px;
  width: 100%;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  font-family: "Fira Code", "Courier New", monospace;
}
.mtr-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid rgba(189, 147, 249, 0.2);
}
.mtr-close {
  background: transparent;
  border: none;
  color: #e2e8f0;
  font-size: 1.5rem;
  line-height: 1;
  cursor: pointer;
  padding: 0 0.5rem;
}
.mtr-close:hover { color: #ff5555; }
.mtr-modal-body {
  padding: 1rem;
  overflow: auto;
  color: #e2e8f0;
}
.mtr-output {
  color: #8be9fd;
  font-family: "Fira Code", "Courier New", monospace;
  font-size: 0.85rem;
  white-space: pre;
  margin: 0;
}
</style>
