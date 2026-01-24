<template>
  <div class="page">
    <h1>История операций</h1>
    <p class="subtitle">Журнал всех выполненных операций</p>

    <!-- Stats cards -->
    <div class="stats-row" v-if="stats">
      <div class="stat-card">
        <div class="stat-value">{{ stats.total_operations }}</div>
        <div class="stat-label">Всего операций</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.last_24h }}</div>
        <div class="stat-label">За 24 часа</div>
      </div>
      <div class="stat-card success">
        <div class="stat-value">{{ stats.by_status?.success || 0 }}</div>
        <div class="stat-label">Успешных</div>
      </div>
      <div class="stat-card error">
        <div class="stat-value">{{ stats.by_status?.error || 0 }}</div>
        <div class="stat-label">Ошибок</div>
      </div>
    </div>

    <!-- Filters -->
    <div class="filters">
      <select v-model="filterOperation" @change="loadHistory">
        <option value="">Все операции</option>
        <option value="devices">Devices</option>
        <option value="mac">MAC</option>
        <option value="lldp">LLDP/CDP</option>
        <option value="interfaces">Interfaces</option>
        <option value="inventory">Inventory</option>
        <option value="sync">Sync NetBox</option>
        <option value="pipeline:default">Pipeline</option>
        <option value="backup">Backup</option>
      </select>
      <select v-model="filterStatus" @change="loadHistory">
        <option value="">Все статусы</option>
        <option value="success">Успех</option>
        <option value="error">Ошибка</option>
        <option value="partial">Частично</option>
      </select>
      <button class="btn-refresh" @click="loadHistory" :disabled="loading">
        {{ loading ? '...' : 'Обновить' }}
      </button>
      <button class="btn-clear" @click="clearHistory" v-if="history.length">
        Очистить
      </button>
    </div>

    <!-- History list -->
    <div class="history-list" v-if="history.length">
      <div
        v-for="entry in history"
        :key="entry.id"
        class="history-item"
        :class="entry.status"
        @click="toggleDetails(entry.id)"
      >
        <div class="item-main">
          <span class="item-time">{{ formatTime(entry.timestamp) }}</span>
          <span class="item-operation" :class="entry.operation">{{ entry.operation }}</span>
          <span class="item-status" :class="entry.status">{{ entry.status }}</span>
          <span class="item-devices" v-if="entry.device_count">
            {{ entry.device_count }} устройств
          </span>
          <span class="item-duration" v-if="entry.duration_ms">
            {{ (entry.duration_ms / 1000).toFixed(1) }}s
          </span>
        </div>

        <!-- Details (expanded) -->
        <div v-if="expandedId === entry.id" class="item-details">
          <div v-if="entry.devices && entry.devices.length" class="detail-row">
            <span class="detail-label">Устройства:</span>
            <span class="detail-value">{{ entry.devices.join(', ') }}</span>
          </div>

          <!-- Stats для sync -->
          <div v-if="entry.stats && !isPipelineEntry(entry)" class="detail-row">
            <span class="detail-label">Статистика:</span>
            <div class="stats-badges">
              <template v-for="(stat, key) in entry.stats" :key="key">
                <span v-if="stat.created" class="badge created">{{ key }}: +{{ stat.created }}</span>
                <span v-if="stat.updated" class="badge updated">{{ key }}: ~{{ stat.updated }}</span>
                <span v-if="stat.deleted" class="badge deleted">{{ key }}: -{{ stat.deleted }}</span>
              </template>
            </div>
          </div>

          <!-- Stats для pipeline (по шагам) -->
          <div v-if="entry.stats && isPipelineEntry(entry)" class="pipeline-stats">
            <div v-for="(stepStats, stepId) in entry.stats" :key="stepId" class="step-stats">
              <div class="step-header">
                <strong>{{ stepId }}</strong>
                <span class="stats-badges">
                  <span v-if="stepStats.created" class="badge created">+{{ stepStats.created }}</span>
                  <span v-if="stepStats.updated" class="badge updated">~{{ stepStats.updated }}</span>
                  <span v-if="stepStats.deleted" class="badge deleted">-{{ stepStats.deleted }}</span>
                  <span v-if="stepStats.skipped" class="badge skipped">={{ stepStats.skipped }}</span>
                </span>
              </div>
              <!-- Детали шага -->
              <div v-if="stepStats.details" class="step-details-content">
                <div v-if="stepStats.details.create && stepStats.details.create.length" class="details-group">
                  <span class="details-label created">Создано:</span>
                  <span v-for="(item, i) in stepStats.details.create" :key="'c'+i" class="detail-chip">
                    {{ formatDetailItem(item) }}
                  </span>
                </div>
                <div v-if="stepStats.details.update && stepStats.details.update.length" class="details-group">
                  <span class="details-label updated">Обновлено:</span>
                  <span v-for="(item, i) in stepStats.details.update" :key="'u'+i" class="detail-chip">
                    {{ formatDetailItem(item) }}
                  </span>
                </div>
                <div v-if="stepStats.details.delete && stepStats.details.delete.length" class="details-group">
                  <span class="details-label deleted">Удалено:</span>
                  <span v-for="(item, i) in stepStats.details.delete" :key="'d'+i" class="detail-chip">
                    {{ formatDetailItem(item) }}
                  </span>
                </div>
                <div v-if="stepStats.details.skip && stepStats.details.skip.length" class="details-group">
                  <span class="details-label skipped">Пропущено:</span>
                  <span v-for="(item, i) in stepStats.details.skip" :key="'s'+i" class="detail-chip" :title="item.reason">
                    {{ item.name }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Details для sync (diff) -->
          <div v-if="entry.details && Array.isArray(entry.details) && entry.details.length" class="diff-details">
            <div class="detail-label">Изменения ({{ entry.details.length }}):</div>
            <div class="diff-list">
              <div v-for="(d, i) in entry.details" :key="i" class="diff-item" :class="d.action">
                <span class="action-badge">{{ d.action }}</span>
                <span class="entity-type">{{ d.entity_type }}</span>
                <span class="entity-name">{{ d.entity_name }}</span>
                <span v-if="d.field" class="field-change">
                  {{ d.field }}: {{ d.old_value }} → {{ d.new_value }}
                </span>
                <span v-if="d.device" class="device">@ {{ d.device }}</span>
              </div>
            </div>
          </div>

          <div v-if="entry.error" class="detail-row error">
            <span class="detail-label">Ошибка:</span>
            <span class="detail-value">{{ entry.error }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      <p v-if="loading">Загрузка...</p>
      <p v-else>Нет записей в истории</p>
    </div>

    <!-- Pagination -->
    <div class="pagination" v-if="total > limit">
      <button @click="prevPage" :disabled="offset === 0">← Назад</button>
      <span>{{ Math.floor(offset / limit) + 1 }} / {{ Math.ceil(total / limit) }}</span>
      <button @click="nextPage" :disabled="offset + limit >= total">Вперёд →</button>
    </div>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'History',
  data() {
    return {
      history: [],
      stats: null,
      total: 0,
      limit: 50,
      offset: 0,
      loading: false,
      filterOperation: '',
      filterStatus: '',
      expandedId: null,
    }
  },
  async mounted() {
    await Promise.all([this.loadHistory(), this.loadStats()])
  },
  methods: {
    async loadHistory() {
      this.loading = true
      try {
        const params = new URLSearchParams({
          limit: this.limit,
          offset: this.offset,
        })
        if (this.filterOperation) params.append('operation', this.filterOperation)
        if (this.filterStatus) params.append('status', this.filterStatus)

        const res = await axios.get(`/api/history/?${params}`)
        this.history = res.data.entries
        this.total = res.data.total
      } catch (e) {
        console.error('Failed to load history:', e)
      } finally {
        this.loading = false
      }
    },
    async loadStats() {
      try {
        const res = await axios.get('/api/history/stats')
        this.stats = res.data
      } catch (e) {
        console.error('Failed to load stats:', e)
      }
    },
    async clearHistory() {
      if (!confirm('Очистить всю историю?')) return
      try {
        await axios.delete('/api/history/')
        this.history = []
        this.total = 0
        await this.loadStats()
      } catch (e) {
        console.error('Failed to clear history:', e)
      }
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
    toggleDetails(id) {
      this.expandedId = this.expandedId === id ? null : id
    },
    prevPage() {
      if (this.offset >= this.limit) {
        this.offset -= this.limit
        this.loadHistory()
      }
    },
    nextPage() {
      if (this.offset + this.limit < this.total) {
        this.offset += this.limit
        this.loadHistory()
      }
    },
    isPipelineEntry(entry) {
      return entry.operation && entry.operation.startsWith('pipeline:')
    },
    formatDetailItem(item) {
      if (typeof item === 'string') return item
      // IP адрес с primary
      if (item.address) {
        let text = item.address
        if (item.interface) text += ` (${item.interface})`
        if (item.is_primary) text += ' [PRIMARY]'
        return text
      }
      // Интерфейс
      if (item.name) {
        let text = item.name
        if (item.device) text = `${item.device}:${item.name}`
        if (item.changes) text += ` [${Object.keys(item.changes).join(', ')}]`
        return text
      }
      return JSON.stringify(item)
    },
  },
}
</script>

<style scoped>
.page h1 { margin-bottom: 10px; }
.subtitle { color: #666; margin-bottom: 20px; }

.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 15px;
  margin-bottom: 20px;
}

.stat-card {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  text-align: center;
}

.stat-card.success { border-left: 4px solid #27ae60; }
.stat-card.error { border-left: 4px solid #e74c3c; }

.stat-value {
  font-size: 28px;
  font-weight: 600;
  color: #2c3e50;
}

.stat-label {
  font-size: 13px;
  color: #666;
  margin-top: 5px;
}

.filters {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.filters select {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.btn-refresh, .btn-clear {
  padding: 8px 16px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 14px;
}

.btn-refresh:hover { background: #f8f9fa; }
.btn-clear { color: #c0392b; border-color: #c0392b; }
.btn-clear:hover { background: #f8d7da; }

.history-list {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.history-item {
  padding: 15px 20px;
  border-bottom: 1px solid #eee;
  cursor: pointer;
  transition: background 0.2s;
}

.history-item:hover { background: #f8f9fa; }
.history-item:last-child { border-bottom: none; }

.history-item.success { border-left: 3px solid #27ae60; }
.history-item.error { border-left: 3px solid #e74c3c; }
.history-item.partial { border-left: 3px solid #f39c12; }

.item-main {
  display: flex;
  align-items: center;
  gap: 15px;
  flex-wrap: wrap;
}

.item-time {
  color: #888;
  font-size: 13px;
  min-width: 100px;
}

.item-operation {
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  background: #e9ecef;
  color: #495057;
}

.item-operation.devices { background: #e3f2fd; color: #1565c0; }
.item-operation.mac { background: #f3e5f5; color: #7b1fa2; }
.item-operation.lldp { background: #e8f5e9; color: #2e7d32; }
.item-operation.interfaces { background: #fff3e0; color: #e65100; }
.item-operation.inventory { background: #fce4ec; color: #c2185b; }
.item-operation.sync { background: #e0f7fa; color: #00838f; }
.item-operation.backup { background: #efebe9; color: #5d4037; }

.item-status {
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.item-status.success { background: #d4edda; color: #155724; }
.item-status.error { background: #f8d7da; color: #721c24; }
.item-status.partial { background: #fff3cd; color: #856404; }

.item-devices, .item-duration {
  color: #666;
  font-size: 13px;
}

.item-details {
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px dashed #ddd;
}

.detail-row {
  display: flex;
  gap: 10px;
  margin-bottom: 8px;
  font-size: 13px;
}

.detail-row.error { color: #c0392b; }

.detail-label {
  font-weight: 500;
  color: #555;
  min-width: 100px;
}

.detail-value {
  color: #333;
}

.stats-badges {
  display: flex;
  gap: 8px;
}

.badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.badge.created { background: #d4edda; color: #155724; }
.badge.updated { background: #cce5ff; color: #004085; }
.badge.deleted { background: #f8d7da; color: #721c24; }
.badge.skipped { background: #e2e3e5; color: #383d41; }
.badge.total { background: #e9ecef; color: #495057; }

.empty-state {
  text-align: center;
  padding: 40px;
  color: #666;
  background: white;
  border-radius: 8px;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 20px;
  margin-top: 20px;
}

.pagination button {
  padding: 8px 16px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  cursor: pointer;
}

.pagination button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pagination span {
  color: #666;
  font-size: 14px;
}

/* Pipeline stats */
.pipeline-stats {
  margin-top: 10px;
}

.step-stats {
  padding: 10px;
  background: #f8f9fa;
  border-radius: 4px;
  margin-bottom: 8px;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.step-details-content {
  padding-left: 10px;
  border-left: 2px solid #e9ecef;
}

.details-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.details-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}
.details-label.created { color: #28a745; }
.details-label.updated { color: #007bff; }

.detail-chip {
  font-size: 11px;
  padding: 2px 6px;
  background: white;
  border-radius: 3px;
  border: 1px solid #e9ecef;
}

.more {
  font-size: 11px;
  color: #6c757d;
  font-style: italic;
}

/* Diff details */
.diff-details {
  margin-top: 15px;
}

.diff-list {
  margin-top: 8px;
}

.diff-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  margin-bottom: 4px;
  background: #f8f9fa;
  border-radius: 4px;
  font-size: 12px;
}

.diff-item.create, .diff-item.created { border-left: 3px solid #28a745; }
.diff-item.update, .diff-item.updated { border-left: 3px solid #007bff; }
.diff-item.delete, .diff-item.deleted { border-left: 3px solid #dc3545; }

.action-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  text-transform: uppercase;
  font-weight: 600;
}
.diff-item.create .action-badge, .diff-item.created .action-badge { background: #d4edda; color: #155724; }
.diff-item.update .action-badge, .diff-item.updated .action-badge { background: #cce5ff; color: #004085; }
.diff-item.delete .action-badge, .diff-item.deleted .action-badge { background: #f8d7da; color: #721c24; }

.entity-type {
  color: #6c757d;
}

.entity-name {
  font-weight: 500;
}

.device {
  color: #888;
  font-size: 11px;
}

.more-items {
  color: #6c757d;
  font-style: italic;
  padding: 8px;
}
</style>
