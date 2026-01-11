<template>
  <div class="page">
    <h1>Devices</h1>
    <p class="subtitle">Сбор информации об устройствах (show version)</p>

    <div class="form-card">
      <form @submit.prevent="collect">
        <div class="form-group">
          <label>Устройства (IP через запятую, пусто = из config)</label>
          <input v-model="devicesInput" type="text" placeholder="10.0.0.1, 10.0.0.2" />
        </div>
        <button type="submit" class="btn primary" :disabled="loading">
          {{ loading ? 'Загрузка...' : 'Собрать' }}
        </button>
      </form>
    </div>

    <div v-if="error" class="error-box">{{ error }}</div>

    <div v-if="result">
      <div class="result-header">
        <h3>Результат</h3>
        <span class="badge" :class="result.success ? 'success' : 'error'">
          {{ result.success ? 'OK' : 'Error' }}
        </span>
      </div>

      <DataTable
        v-if="result.devices && result.devices.length"
        :data="result.devices"
        :columns="columns"
        export-filename="devices"
      />

      <div v-if="result.errors && result.errors.length" class="errors">
        <h4>Ошибки:</h4>
        <ul>
          <li v-for="e in result.errors" :key="e">{{ e }}</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'
import DataTable from '../components/DataTable.vue'

export default {
  name: 'Devices',
  components: { DataTable },
  data() {
    return {
      devicesInput: '',
      loading: false,
      result: null,
      error: null,
      columns: [
        { key: 'hostname', label: 'Hostname' },
        { key: 'ip_address', label: 'IP' },
        { key: 'platform', label: 'Platform' },
        { key: 'model', label: 'Model' },
        { key: 'serial', label: 'Serial' },
        { key: 'version', label: 'Version' },
        { key: 'uptime', label: 'Uptime' },
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
        const res = await axios.post('/api/devices/collect', { devices })
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

.form-group { margin-bottom: 15px; }
.form-group label { display: block; margin-bottom: 5px; font-weight: 500; }
.form-group input {
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
.btn.primary:hover { background: #2980b9; }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }

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

.errors { margin-top: 15px; }
.errors h4 { color: #c0392b; margin-bottom: 10px; }
.errors ul { padding-left: 20px; }
.errors li { color: #c0392b; }
</style>
