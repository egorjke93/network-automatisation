<template>
  <div class="page">
    <h1>LLDP/CDP Neighbors</h1>
    <p class="subtitle">Сбор соседей по LLDP и CDP</p>

    <div class="form-card">
      <form @submit.prevent="collect">
        <div class="form-row">
          <div class="form-group">
            <label>Устройства (IP через запятую)</label>
            <input v-model="devicesInput" type="text" placeholder="10.0.0.1, 10.0.0.2" />
          </div>
          <div class="form-group">
            <label>Протокол</label>
            <select v-model="protocol">
              <option value="both">Both (LLDP + CDP)</option>
              <option value="lldp">LLDP</option>
              <option value="cdp">CDP</option>
            </select>
          </div>
        </div>
        <button type="submit" class="btn primary" :disabled="loading">
          {{ loading ? 'Загрузка...' : 'Собрать' }}
        </button>
      </form>
    </div>

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
          <span class="protocol-badge" :class="value">{{ value?.toUpperCase() }}</span>
        </template>
      </DataTable>
    </div>
  </div>
</template>

<script>
import axios from 'axios'
import DataTable from '../components/DataTable.vue'

export default {
  name: 'Lldp',
  components: { DataTable },
  data() {
    return {
      devicesInput: '',
      protocol: 'both',
      loading: false,
      result: null,
      error: null,
      columns: [
        { key: 'hostname', label: 'Hostname' },
        { key: 'local_interface', label: 'Local Port' },
        { key: 'remote_hostname', label: 'Remote Hostname' },
        { key: 'remote_port', label: 'Remote Port' },
        { key: 'remote_ip', label: 'Remote IP' },
        { key: 'protocol', label: 'Protocol' },
      ],
    }
  },
  methods: {
    async collect() {
      this.loading = true
      this.error = null
      this.result = null

      const devices = this.devicesInput
        ? this.devicesInput.split(',').map(d => d.trim()).filter(Boolean)
        : []

      try {
        const res = await axios.post('/api/lldp/collect', { devices, protocol: this.protocol })
        this.result = res.data
      } catch (e) {
        this.error = e.response?.data?.detail || e.message
      } finally {
        this.loading = false
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

.form-row {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 15px;
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
</style>
