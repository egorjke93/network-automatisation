<template>
  <div class="page">
    <h1>LLDP/CDP Neighbors</h1>
    <p class="subtitle">Сбор соседей по LLDP и CDP</p>

    <div class="form-card">
      <form @submit.prevent="collect">
        <DeviceSelector v-model="selectedDevices" />
        <div class="form-group">
          <label>Протокол</label>
          <select v-model="protocol">
            <option value="both">Both (LLDP + CDP)</option>
            <option value="lldp">LLDP</option>
            <option value="cdp">CDP</option>
          </select>
        </div>
        <button type="submit" class="btn primary" :disabled="loading">
          {{ loading ? 'Загрузка...' : 'Собрать' }}
        </button>
      </form>
    </div>

    <ProgressBar :task-id="taskId" @complete="onTaskComplete" />

    <div v-if="error" class="error-box">{{ error }}</div>

    <div v-if="result">
      <div class="result-header">
        <h3>Соседи ({{ result.total }})</h3>
        <span class="badge" :class="result.success ? 'success' : 'error'">
          {{ result.success ? 'OK' : 'Error' }}
        </span>
      </div>

      <DataTable
        v-if="result.neighbors && result.neighbors.length"
        :data="result.neighbors"
        :columns="columns"
        export-filename="lldp_neighbors"
      >
        <template #cell-protocol="{ value }">
          <span class="protocol-badge" :class="value?.toLowerCase()">{{ value }}</span>
        </template>
      </DataTable>
    </div>
  </div>
</template>

<script>
import axios from 'axios'
import DataTable from '../components/DataTable.vue'
import ProgressBar from '../components/ProgressBar.vue'
import DeviceSelector from '../components/DeviceSelector.vue'

export default {
  name: 'Lldp',
  components: { DataTable, ProgressBar, DeviceSelector },
  data() {
    return {
      selectedDevices: [],
      protocol: 'both',
      loading: false,
      result: null,
      error: null,
      taskId: null,
      columns: [],  // Загружаются из API
    }
  },
  async mounted() {
    await this.loadColumns()
  },
  methods: {
    async loadColumns() {
      try {
        const res = await axios.get('/api/fields/lldp')
        this.columns = res.data.columns
      } catch (e) {
        console.error('Failed to load columns:', e)
        this.columns = [
          { key: 'hostname', label: 'Hostname' },
          { key: 'remote_hostname', label: 'Neighbor' },
        ]
      }
    },
    async collect() {
      this.loading = true
      this.error = null
      this.result = null
      this.taskId = null

      try {
        const res = await axios.post('/api/lldp/collect', {
          devices: this.selectedDevices,
          protocol: this.protocol,
          async_mode: true,
        })
        this.taskId = res.data.task_id
      } catch (e) {
        this.error = e.response?.data?.detail || e.message
        this.loading = false
      }
    },
    onTaskComplete(task) {
      this.loading = false
      if (task.status === 'completed' && task.result?.data) {
        this.result = {
          success: true,
          total: task.result.total || task.result.data.length,
          neighbors: task.result.data,  // Данные уже в правильном формате
        }
      } else if (task.status === 'failed') {
        this.error = task.error || 'Ошибка сбора данных'
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
.form-group input, .form-group select {
  width: 100%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
}
.btn.primary { background: #3498db; color: white; }
.btn:disabled { opacity: 0.6; }

.error-box {
  background: #f8d7da;
  color: #721c24;
  padding: 15px;
  border-radius: 4px;
  margin-bottom: 20px;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 15px;
}

.badge {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  color: white;
}
.badge.success { background: #27ae60; }
.badge.error { background: #e74c3c; }

.protocol-badge {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  color: white;
}
.protocol-badge.lldp { background: #3498db; }
.protocol-badge.cdp { background: #9b59b6; }
.protocol-badge.both { background: #27ae60; }
</style>
