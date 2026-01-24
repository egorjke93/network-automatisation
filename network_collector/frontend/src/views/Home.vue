<template>
  <div class="dashboard">
    <h1>Dashboard</h1>
    <p class="subtitle">Network Collector - обзор системы</p>

    <!-- API Status -->
    <div class="status-bar" :class="health ? 'online' : 'offline'">
      <span class="status-indicator"></span>
      <span v-if="health">
        API Online | v{{ health.version }} | Uptime: {{ formatUptime(health.uptime) }}
      </span>
      <span v-else>API Offline</span>
      <button class="reload-btn" @click="reloadConfig" :disabled="reloading" title="Reload fields.yaml">
        {{ reloading ? '...' : '↻ Config' }}
      </button>
      <span v-if="reloadMessage" :class="['reload-msg', reloadSuccess ? 'ok' : 'err']">
        {{ reloadMessage }}
      </span>
    </div>

    <!-- Main Stats -->
    <div class="stats-grid">
      <div class="stat-card primary">
        <div class="stat-icon">&#128187;</div>
        <div class="stat-content">
          <div class="stat-value">{{ deviceCount }}</div>
          <div class="stat-label">Устройств в конфиге</div>
        </div>
      </div>

      <div class="stat-card success">
        <div class="stat-icon">&#9989;</div>
        <div class="stat-content">
          <div class="stat-value">{{ historyStats?.by_status?.success || 0 }}</div>
          <div class="stat-label">Успешных операций</div>
        </div>
      </div>

      <div class="stat-card warning">
        <div class="stat-icon">&#128337;</div>
        <div class="stat-content">
          <div class="stat-value">{{ historyStats?.last_24h || 0 }}</div>
          <div class="stat-label">За последние 24ч</div>
        </div>
      </div>

      <div class="stat-card" :class="historyStats?.by_status?.error ? 'danger' : ''">
        <div class="stat-icon">&#10060;</div>
        <div class="stat-content">
          <div class="stat-value">{{ historyStats?.by_status?.error || 0 }}</div>
          <div class="stat-label">Ошибок</div>
        </div>
      </div>
    </div>

    <!-- Operations by type -->
    <div class="section" v-if="historyStats?.by_operation">
      <h3>Операции по типам</h3>
      <div class="operations-grid">
        <div
          v-for="(count, op) in historyStats.by_operation"
          :key="op"
          class="operation-card"
          :class="op"
        >
          <span class="op-name">{{ op }}</span>
          <span class="op-count">{{ count }}</span>
        </div>
      </div>
    </div>

    <!-- Quick Actions -->
    <div class="section">
      <h3>Быстрые действия</h3>
      <div class="actions-grid">
        <router-link to="/devices" class="action-card">
          <div class="action-icon">&#128421;</div>
          <div class="action-title">Devices</div>
          <div class="action-desc">Сбор show version</div>
        </router-link>

        <router-link to="/mac" class="action-card">
          <div class="action-icon">&#128279;</div>
          <div class="action-title">MAC Table</div>
          <div class="action-desc">Таблица MAC-адресов</div>
        </router-link>

        <router-link to="/lldp" class="action-card">
          <div class="action-icon">&#128257;</div>
          <div class="action-title">LLDP/CDP</div>
          <div class="action-desc">Соседи</div>
        </router-link>

        <router-link to="/interfaces" class="action-card">
          <div class="action-icon">&#128268;</div>
          <div class="action-title">Interfaces</div>
          <div class="action-desc">Интерфейсы</div>
        </router-link>

        <router-link to="/sync" class="action-card highlight">
          <div class="action-icon">&#128259;</div>
          <div class="action-title">Sync NetBox</div>
          <div class="action-desc">Синхронизация</div>
        </router-link>

        <router-link to="/history" class="action-card">
          <div class="action-icon">&#128195;</div>
          <div class="action-title">History</div>
          <div class="action-desc">Журнал операций</div>
        </router-link>

        <router-link to="/device-management" class="action-card">
          <div class="action-icon">&#9881;</div>
          <div class="action-title">Devices Config</div>
          <div class="action-desc">Управление устройствами</div>
        </router-link>
      </div>
    </div>

    <!-- Recent Activity -->
    <div class="section" v-if="recentHistory.length">
      <div class="section-header">
        <h3>Последние операции</h3>
        <router-link to="/history" class="view-all">Все →</router-link>
      </div>
      <div class="recent-list">
        <div
          v-for="entry in recentHistory"
          :key="entry.id"
          class="recent-item"
          :class="entry.status"
        >
          <span class="recent-time">{{ formatTime(entry.timestamp) }}</span>
          <span class="recent-op" :class="entry.operation">{{ entry.operation }}</span>
          <span class="recent-status" :class="entry.status">{{ entry.status }}</span>
          <span class="recent-devices" v-if="entry.device_count">
            {{ entry.device_count }} устройств
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'Home',
  data() {
    return {
      health: null,
      deviceCount: 0,
      historyStats: null,
      recentHistory: [],
      reloading: false,
      reloadMessage: '',
      reloadSuccess: false,
    }
  },
  async mounted() {
    await Promise.all([
      this.checkHealth(),
      this.loadDeviceCount(),
      this.loadHistoryStats(),
      this.loadRecentHistory(),
    ])
  },
  methods: {
    async checkHealth() {
      try {
        const res = await axios.get('/health')
        this.health = res.data
      } catch {
        this.health = null
      }
    },
    async loadDeviceCount() {
      try {
        const res = await axios.get('/api/device-management/stats')
        this.deviceCount = res.data.enabled || res.data.total || 0
      } catch {
        // Fallback to devices list
        try {
          const res = await axios.get('/api/devices/list')
          this.deviceCount = res.data.devices?.length || 0
        } catch {
          this.deviceCount = 0
        }
      }
    },
    async loadHistoryStats() {
      try {
        const res = await axios.get('/api/history/stats')
        this.historyStats = res.data
      } catch {
        this.historyStats = null
      }
    },
    async loadRecentHistory() {
      try {
        const res = await axios.get('/api/history/?limit=5')
        this.recentHistory = res.data.entries || []
      } catch {
        this.recentHistory = []
      }
    },
    formatUptime(seconds) {
      if (!seconds) return '-'
      const hours = Math.floor(seconds / 3600)
      const minutes = Math.floor((seconds % 3600) / 60)
      return `${hours}h ${minutes}m`
    },
    formatTime(timestamp) {
      if (!timestamp) return '-'
      const date = new Date(timestamp)
      return date.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    },
    async reloadConfig() {
      this.reloading = true
      this.reloadMessage = ''
      try {
        await axios.post('/api/fields/reload')
        this.reloadSuccess = true
        this.reloadMessage = 'OK'
      } catch (e) {
        this.reloadSuccess = false
        this.reloadMessage = 'Error'
      } finally {
        this.reloading = false
        setTimeout(() => { this.reloadMessage = '' }, 2000)
      }
    },
  },
}
</script>

<style scoped>
.dashboard h1 { margin-bottom: 10px; }
.subtitle { color: #666; margin-bottom: 20px; }

.status-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 20px;
  border-radius: 8px;
  margin-bottom: 25px;
  font-size: 14px;
}

.status-bar.online {
  background: #d4edda;
  color: #155724;
}

.status-bar.offline {
  background: #f8d7da;
  color: #721c24;
}

.status-indicator {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.online .status-indicator { background: #27ae60; }
.offline .status-indicator { background: #e74c3c; }

.reload-btn {
  margin-left: auto;
  padding: 4px 12px;
  border: 1px solid currentColor;
  border-radius: 4px;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  opacity: 0.8;
}
.reload-btn:hover { opacity: 1; background: rgba(255,255,255,0.3); }
.reload-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.reload-msg { font-size: 12px; margin-left: 8px; }
.reload-msg.ok { color: #155724; }
.reload-msg.err { color: #721c24; }

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 15px;
  background: white;
  padding: 20px;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: transform 0.2s;
}

.stat-card:hover { transform: translateY(-2px); }

.stat-card.primary { border-left: 4px solid #3498db; }
.stat-card.success { border-left: 4px solid #27ae60; }
.stat-card.warning { border-left: 4px solid #f39c12; }
.stat-card.danger { border-left: 4px solid #e74c3c; }

.stat-icon {
  font-size: 28px;
  opacity: 0.8;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: #2c3e50;
}

.stat-label {
  font-size: 13px;
  color: #666;
  margin-top: 2px;
}

/* Sections */
.section {
  background: white;
  padding: 20px;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  margin-bottom: 25px;
}

.section h3 {
  margin-bottom: 15px;
  font-size: 16px;
  color: #2c3e50;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.section-header h3 { margin: 0; }

.view-all {
  color: #3498db;
  text-decoration: none;
  font-size: 14px;
}

.view-all:hover { text-decoration: underline; }

/* Operations Grid */
.operations-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.operation-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 15px;
  border-radius: 8px;
  background: #f8f9fa;
}

.op-name {
  font-weight: 500;
  text-transform: capitalize;
}

.op-count {
  background: white;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
  font-size: 13px;
}

.operation-card.devices { background: #e3f2fd; }
.operation-card.mac { background: #f3e5f5; }
.operation-card.lldp { background: #e8f5e9; }
.operation-card.interfaces { background: #fff3e0; }
.operation-card.inventory { background: #fce4ec; }
.operation-card.sync { background: #e0f7fa; }
.operation-card.backup { background: #efebe9; }

/* Actions Grid */
.actions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 15px;
}

.action-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 15px;
  background: #f8f9fa;
  border-radius: 10px;
  text-decoration: none;
  color: #2c3e50;
  transition: all 0.2s;
  border: 2px solid transparent;
}

.action-card:hover {
  background: #e9ecef;
  border-color: #3498db;
  transform: translateY(-2px);
}

.action-card.highlight {
  background: #e3f2fd;
  border-color: #3498db;
}

.action-icon {
  font-size: 28px;
  margin-bottom: 8px;
}

.action-title {
  font-weight: 600;
  font-size: 14px;
}

.action-desc {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
}

/* Recent List */
.recent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 15px;
  background: #f8f9fa;
  border-radius: 6px;
  font-size: 13px;
}

.recent-item.success { border-left: 3px solid #27ae60; }
.recent-item.error { border-left: 3px solid #e74c3c; }

.recent-time {
  color: #888;
  min-width: 90px;
}

.recent-op {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  background: #e9ecef;
}

.recent-op.devices { background: #e3f2fd; color: #1565c0; }
.recent-op.mac { background: #f3e5f5; color: #7b1fa2; }
.recent-op.lldp { background: #e8f5e9; color: #2e7d32; }
.recent-op.sync { background: #e0f7fa; color: #00838f; }

.recent-status {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
}

.recent-status.success { background: #d4edda; color: #155724; }
.recent-status.error { background: #f8d7da; color: #721c24; }

.recent-devices {
  color: #666;
  margin-left: auto;
}
</style>
