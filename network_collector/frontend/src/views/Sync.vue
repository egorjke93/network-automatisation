<template>
  <div class="page">
    <h1>Sync NetBox</h1>
    <p class="subtitle">Синхронизация с NetBox</p>

    <div class="form-card">
      <form @submit.prevent="runSync">
        <DeviceSelector v-model="selectedDevices" />
        <div class="form-group">
          <label>Site</label>
          <input v-model="site" type="text" placeholder="Office" />
        </div>

        <div class="form-section">
          <h4>Что синхронизировать (CREATE / UPDATE)</h4>
          <div class="checkboxes">
            <label class="checkbox">
              <input type="checkbox" v-model="syncAll" />
              <span>Sync All</span>
            </label>
            <label class="checkbox">
              <input type="checkbox" v-model="createDevices" :disabled="syncAll" />
              <span>Create Devices</span>
            </label>
            <label class="checkbox">
              <input type="checkbox" v-model="updateDevices" :disabled="syncAll" />
              <span>Update Devices</span>
            </label>
            <label class="checkbox">
              <input type="checkbox" v-model="interfaces" :disabled="syncAll" />
              <span>Interfaces</span>
            </label>
            <label class="checkbox">
              <input type="checkbox" v-model="ipAddresses" :disabled="syncAll" />
              <span>IP Addresses</span>
            </label>
            <label class="checkbox">
              <input type="checkbox" v-model="updateIps" :disabled="syncAll || !ipAddresses" />
              <span>Update IPs</span>
            </label>
            <label class="checkbox">
              <input type="checkbox" v-model="vlans" :disabled="syncAll" />
              <span>VLANs</span>
            </label>
            <label class="checkbox">
              <input type="checkbox" v-model="inventory" :disabled="syncAll" />
              <span>Inventory</span>
            </label>
            <label class="checkbox">
              <input type="checkbox" v-model="cables" :disabled="syncAll" />
              <span>Cables</span>
            </label>
          </div>

          <!-- Protocol for cables -->
          <div class="protocol-select" v-if="cables || syncAll">
            <label>Протокол:</label>
            <select v-model="protocol">
              <option value="both">LLDP + CDP</option>
              <option value="lldp">Только LLDP</option>
              <option value="cdp">Только CDP</option>
            </select>
          </div>
        </div>

        <!-- CLEANUP SECTION -->
        <div class="form-section danger-section">
          <h4>Удаление (DELETE)</h4>
          <p class="warning-text">Удаляет объекты из NetBox которых нет на устройствах</p>
          <div class="checkboxes">
            <label class="checkbox danger">
              <input type="checkbox" v-model="cleanupInterfaces" />
              <span>Cleanup Interfaces</span>
            </label>
            <label class="checkbox danger">
              <input type="checkbox" v-model="cleanupIps" />
              <span>Cleanup IPs</span>
            </label>
            <label class="checkbox danger">
              <input type="checkbox" v-model="cleanupCables" />
              <span>Cleanup Cables</span>
            </label>
            <label class="checkbox danger">
              <input type="checkbox" v-model="cleanupInventory" />
              <span>Cleanup Inventory</span>
            </label>
          </div>
        </div>

        <div class="actions-row">
          <button type="submit" class="btn primary" :disabled="loading">
            {{ loading ? 'Загрузка...' : 'Preview Changes' }}
          </button>
        </div>
      </form>
    </div>

    <ProgressBar :task-id="taskId" @complete="onTaskComplete" />

    <div v-if="error" class="error-box">{{ error }}</div>

    <div v-if="result" class="result">
      <div class="result-header">
        <h3>{{ result.dry_run ? 'Preview изменений' : 'Результат синхронизации' }}</h3>
        <span class="badge" :class="result.success ? 'success' : 'error'">
          {{ result.success ? 'OK' : 'Error' }}
        </span>
        <span class="badge dry-run" v-if="result.dry_run">PREVIEW</span>
      </div>

      <!-- Note about new devices + interfaces -->
      <div v-if="result.dry_run && result.devices?.created && (interfaces || syncAll)" class="info-note">
        Интерфейсы будут синхронизированы после создания устройств
      </div>

      <!-- Stats -->
      <div class="stats-grid">
        <div class="stat-card" v-if="hasStats(result.devices)">
          <h4>Devices</h4>
          <div class="stat-values">
            <span class="created" v-if="result.devices.created" title="Создано">+{{ result.devices.created }} new</span>
            <span class="updated" v-if="result.devices.updated" title="Обновлено">~{{ result.devices.updated }} upd</span>
            <span class="deleted" v-if="result.devices.deleted" title="Удалено">-{{ result.devices.deleted }} del</span>
            <span class="skipped" v-if="result.devices.skipped" title="Пропущено">{{ result.devices.skipped }} skip</span>
          </div>
        </div>
        <div class="stat-card" v-if="hasStats(result.interfaces)">
          <h4>Interfaces</h4>
          <div class="stat-values">
            <span class="created" v-if="result.interfaces.created" title="Создано">+{{ result.interfaces.created }} new</span>
            <span class="updated" v-if="result.interfaces.updated" title="Обновлено">~{{ result.interfaces.updated }} upd</span>
            <span class="deleted" v-if="result.interfaces.deleted" title="Удалено">-{{ result.interfaces.deleted }} del</span>
            <span class="skipped" v-if="result.interfaces.skipped" title="Пропущено">{{ result.interfaces.skipped }} skip</span>
          </div>
        </div>
        <div class="stat-card" v-if="hasStats(result.ip_addresses)">
          <h4>IP Addresses</h4>
          <div class="stat-values">
            <span class="created" v-if="result.ip_addresses.created" title="Создано">+{{ result.ip_addresses.created }} new</span>
            <span class="updated" v-if="result.ip_addresses.updated" title="Обновлено">~{{ result.ip_addresses.updated }} upd</span>
            <span class="deleted" v-if="result.ip_addresses.deleted" title="Удалено">-{{ result.ip_addresses.deleted }} del</span>
            <span class="skipped" v-if="result.ip_addresses.skipped" title="Пропущено">{{ result.ip_addresses.skipped }} skip</span>
          </div>
        </div>
        <div class="stat-card" v-if="hasStats(result.vlans)">
          <h4>VLANs</h4>
          <div class="stat-values">
            <span class="created" v-if="result.vlans.created" title="Создано">+{{ result.vlans.created }} new</span>
            <span class="skipped" v-if="result.vlans.skipped" title="Пропущено">{{ result.vlans.skipped }} skip</span>
          </div>
        </div>
        <div class="stat-card" v-if="hasStats(result.inventory)">
          <h4>Inventory</h4>
          <div class="stat-values">
            <span class="created" v-if="result.inventory.created" title="Создано">+{{ result.inventory.created }} new</span>
            <span class="updated" v-if="result.inventory.updated" title="Обновлено">~{{ result.inventory.updated }} upd</span>
            <span class="skipped" v-if="result.inventory.skipped" title="Пропущено">{{ result.inventory.skipped }} skip</span>
          </div>
        </div>
        <div class="stat-card" v-if="hasStats(result.cables)">
          <h4>Cables</h4>
          <div class="stat-values">
            <span class="created" v-if="result.cables.created" title="Создано">+{{ result.cables.created }} new</span>
            <span class="deleted" v-if="result.cables.deleted" title="Удалено">-{{ result.cables.deleted }} del</span>
            <span class="skipped" v-if="result.cables.skipped" title="Пропущено">{{ result.cables.skipped }} skip</span>
            <span class="failed" v-if="result.cables.failed" title="Ошибки">{{ result.cables.failed }} err</span>
          </div>
        </div>
      </div>

      <!-- Apply button (only in preview mode) -->
      <div v-if="result.dry_run && hasChanges" class="apply-section">
        <button class="btn success" @click="applyChanges" :disabled="applying">
          {{ applying ? 'Применяю...' : 'Apply Changes' }}
        </button>
        <span class="apply-hint">Применить изменения в NetBox</span>
      </div>

      <!-- Diff with details -->
      <div v-if="result.diff && result.diff.length" class="diff-section">
        <div class="diff-header">
          <h4>Изменения ({{ result.diff.length }})</h4>
          <div class="filter-buttons">
            <button
              v-for="action in ['all', 'create', 'update', 'delete', 'skip']"
              :key="action"
              class="filter-btn"
              :class="{ active: diffFilter === action }"
              @click="diffFilter = action"
            >
              {{ action === 'all' ? 'Все' : action }}
            </button>
          </div>
        </div>

        <div class="diff-list">
          <div
            v-for="(d, i) in filteredDiff"
            :key="i"
            class="diff-item"
            :class="d.action"
          >
            <div class="diff-main">
              <span class="action-badge" :class="d.action">{{ d.action }}</span>
              <span class="entity-type">{{ d.entity_type }}</span>
              <span class="entity-name">{{ d.entity_name }}</span>
              <span class="device" v-if="d.device">@ {{ d.device }}</span>
            </div>
            <!-- Field changes for updates -->
            <div v-if="d.action === 'update' && d.field" class="diff-details">
              <span class="field-name">{{ d.field }}:</span>
              <span class="old-value">{{ formatValue(d.old_value) }}</span>
              <span class="arrow">→</span>
              <span class="new-value">{{ formatValue(d.new_value) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="!hasChanges" class="no-changes">
        Нет изменений для синхронизации
      </div>

      <!-- Errors -->
      <div v-if="result.errors && result.errors.length" class="errors-section">
        <h4>Ошибки</h4>
        <ul>
          <li v-for="e in result.errors" :key="e">{{ e }}</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'
import ProgressBar from '../components/ProgressBar.vue'
import DeviceSelector from '../components/DeviceSelector.vue'

export default {
  name: 'Sync',
  components: { ProgressBar, DeviceSelector },
  data() {
    return {
      selectedDevices: [],
      site: '',
      // CREATE/UPDATE options
      syncAll: false,
      createDevices: true,
      updateDevices: true,
      interfaces: true,
      ipAddresses: false,
      updateIps: false,
      vlans: false,
      inventory: false,
      cables: false,
      protocol: 'both',
      // DELETE options
      cleanupInterfaces: false,
      cleanupIps: false,
      cleanupCables: false,
      cleanupInventory: false,
      // State
      loading: false,
      applying: false,
      result: null,
      error: null,
      diffFilter: 'all',
      taskId: null,
    }
  },
  computed: {
    hasChanges() {
      if (!this.result) return false
      const stats = ['devices', 'interfaces', 'ip_addresses', 'vlans', 'inventory', 'cables']
      return stats.some(s => {
        const stat = this.result[s]
        return stat && (stat.created || stat.updated || stat.deleted)
      })
    },
    filteredDiff() {
      if (!this.result?.diff) return []
      if (this.diffFilter === 'all') return this.result.diff
      return this.result.diff.filter(d => d.action === this.diffFilter)
    },
  },
  methods: {
    hasStats(stat) {
      if (!stat) return false
      return stat.created || stat.updated || stat.deleted || stat.skipped || stat.failed
    },
    formatValue(val) {
      if (val === null || val === undefined) return '(empty)'
      if (val === '') return '(empty)'
      return String(val)
    },
    buildRequest() {
      return {
        devices: this.selectedDevices,
        site: this.site || null,
        // CREATE/UPDATE
        sync_all: this.syncAll,
        create_devices: this.syncAll || this.createDevices,
        update_devices: this.syncAll || this.updateDevices,
        interfaces: this.syncAll || this.interfaces,
        ip_addresses: this.syncAll || this.ipAddresses,
        update_ips: this.updateIps,
        vlans: this.syncAll || this.vlans,
        inventory: this.syncAll || this.inventory,
        cables: this.syncAll || this.cables,
        protocol: this.protocol,
        // DELETE
        cleanup_interfaces: this.cleanupInterfaces,
        cleanup_ips: this.cleanupIps,
        cleanup_cables: this.cleanupCables,
        cleanup_inventory: this.cleanupInventory,
      }
    },
    async runSync() {
      this.loading = true
      this.error = null
      this.result = null
      this.diffFilter = 'all'
      this.taskId = null

      try {
        const res = await axios.post('/api/sync/netbox', {
          ...this.buildRequest(),
          dry_run: true,
          show_diff: true,
          async_mode: true,
        })
        // В async mode сразу получаем task_id, результат придёт позже
        this.taskId = res.data.task_id
        // Не снимаем loading пока task не завершится
      } catch (e) {
        this.error = e.response?.data?.detail || e.message
        this.loading = false
      }
    },
    async applyChanges() {
      if (!confirm('Применить изменения в NetBox?')) return

      this.applying = true
      this.error = null
      this.result = null
      this.taskId = null

      try {
        const res = await axios.post('/api/sync/netbox', {
          ...this.buildRequest(),
          dry_run: false,
          show_diff: true,
          async_mode: true,
        })
        // В async mode сразу получаем task_id
        this.taskId = res.data.task_id
      } catch (e) {
        this.error = e.response?.data?.detail || e.message
        this.applying = false
      }
    },
    onTaskComplete(task) {
      console.log('Task completed:', task)
      this.loading = false
      this.applying = false

      // Получаем результат из task.result
      if (task.result) {
        this.result = {
          success: task.result.success,
          dry_run: task.result.dry_run,
          devices: task.result.stats?.devices || {},
          interfaces: task.result.stats?.interfaces || {},
          ip_addresses: task.result.stats?.ip_addresses || {},
          vlans: task.result.stats?.vlans || {},
          cables: task.result.stats?.cables || {},
          inventory: task.result.stats?.inventory || {},
          diff: task.result.diff || [],
          errors: task.result.errors || [],
        }
      } else if (task.status === 'failed') {
        this.error = task.message || 'Sync failed'
      }
    },
  },
}
</script>

<style scoped>
.page h1 { margin-bottom: 10px; }
.subtitle { color: #666; margin-bottom: 20px; }

.form-card {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 20px;
}

.form-group { margin-bottom: 15px; }
.form-group label { display: block; margin-bottom: 5px; font-weight: 500; }
.form-group input {
  width: 100%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.form-section {
  margin: 20px 0;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 4px;
}

.form-section h4 {
  margin-bottom: 10px;
  font-size: 14px;
}

.checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 15px;
}

.checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
}

.checkbox input { width: 16px; height: 16px; }

.actions-row {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

.btn {
  padding: 12px 24px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
  font-size: 15px;
}
.btn.primary { background: #3498db; color: white; }
.btn.success { background: #27ae60; color: white; }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }

.error-box {
  background: #f8d7da;
  color: #721c24;
  padding: 15px;
  border-radius: 4px;
  margin-bottom: 20px;
}

.result {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
}

.badge {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  color: white;
}
.badge.success { background: #27ae60; }
.badge.error { background: #e74c3c; }
.badge.dry-run { background: #f39c12; }

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 15px;
  margin-bottom: 20px;
}

.stat-card {
  background: #f8f9fa;
  padding: 15px;
  border-radius: 8px;
  text-align: center;
}

.stat-card h4 {
  margin-bottom: 10px;
  font-size: 14px;
  color: #666;
}

.stat-values {
  display: flex;
  justify-content: center;
  gap: 10px;
}

.stat-values span {
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
  font-size: 14px;
}
.stat-values .created { background: #d4edda; color: #155724; }
.stat-values .updated { background: #cce5ff; color: #004085; }
.stat-values .deleted { background: #f8d7da; color: #721c24; }
.stat-values .skipped { background: #6c757d; color: white; }
.stat-values .failed { background: #f8d7da; color: #721c24; }

/* Apply section */
.apply-section {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 15px;
  background: #d4edda;
  border-radius: 8px;
  margin-bottom: 20px;
}

.apply-hint {
  color: #155724;
  font-size: 14px;
}

/* Diff section */
.diff-section {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #eee;
}

.diff-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.diff-header h4 { margin: 0; }

.filter-buttons {
  display: flex;
  gap: 5px;
}

.filter-btn {
  padding: 5px 12px;
  border: 1px solid #ddd;
  background: white;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  text-transform: capitalize;
}

.filter-btn:hover { background: #f8f9fa; }
.filter-btn.active {
  background: #3498db;
  color: white;
  border-color: #3498db;
}

.diff-list {
  max-height: 500px;
  overflow-y: auto;
}

.diff-item {
  padding: 10px 12px;
  border-radius: 4px;
  margin-bottom: 5px;
  font-size: 14px;
}

.diff-item.create { background: #d4edda; }
.diff-item.update { background: #cce5ff; }
.diff-item.delete { background: #f8d7da; }
.diff-item.skip { background: #e9ecef; }

.diff-main {
  display: flex;
  align-items: center;
  gap: 10px;
}

.action-badge {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: white;
}
.action-badge.create { background: #27ae60; }
.action-badge.update { background: #3498db; }
.action-badge.delete { background: #e74c3c; }
.action-badge.skip { background: #6c757d; }

.entity-type { color: #666; }
.entity-name { font-weight: 500; }
.device { color: #888; font-size: 12px; }

.diff-details {
  margin-top: 8px;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 4px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.field-name {
  font-weight: 500;
  color: #555;
}

.old-value {
  color: #c0392b;
  text-decoration: line-through;
}

.arrow {
  color: #888;
}

.new-value {
  color: #27ae60;
  font-weight: 500;
}

.no-changes {
  padding: 30px;
  text-align: center;
  color: #666;
  background: #f8f9fa;
  border-radius: 8px;
}

.info-note {
  padding: 12px 15px;
  background: #e7f3ff;
  border-left: 4px solid #3498db;
  border-radius: 4px;
  color: #004085;
  font-size: 14px;
  margin-bottom: 15px;
}

.errors-section {
  margin-top: 20px;
  padding: 15px;
  background: #f8d7da;
  border-radius: 8px;
}

.errors-section h4 {
  color: #721c24;
  margin-bottom: 10px;
}

.errors-section ul {
  padding-left: 20px;
  color: #721c24;
}

/* Danger section for cleanup */
.danger-section {
  background: #fff5f5 !important;
  border: 1px solid #f5c6cb;
}

.danger-section h4 { color: #721c24; }

.warning-text {
  font-size: 12px;
  color: #856404;
  margin-bottom: 10px;
  padding: 8px;
  background: #fff3cd;
  border-radius: 4px;
}

.checkbox.danger span { color: #721c24; }
.checkbox.danger input:checked + span { font-weight: 600; }

/* Protocol selector */
.protocol-select {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid #ddd;
}

.protocol-select label {
  font-size: 14px;
  color: #666;
}

.protocol-select select {
  padding: 6px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}
</style>
