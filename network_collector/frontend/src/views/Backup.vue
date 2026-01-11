<template>
  <div class="page">
    <h1>Backup</h1>
    <p class="subtitle">Резервное копирование конфигураций</p>

    <div class="form-card">
      <form @submit.prevent="runBackup">
        <div class="form-group">
          <label>Устройства (IP через запятую)</label>
          <input v-model="devicesInput" type="text" placeholder="10.0.0.1, 10.0.0.2" />
        </div>
        <div class="form-group">
          <label>Директория для сохранения</label>
          <input v-model="outputDir" type="text" placeholder="/backups (по умолчанию)" />
        </div>
        <button type="submit" class="btn primary" :disabled="loading">
          {{ loading ? 'Загрузка...' : 'Запустить Backup' }}
        </button>
      </form>
    </div>

    <div v-if="error" class="error-box">{{ error }}</div>

    <div v-if="result" class="result">
      <div class="result-header">
        <h3>Результат</h3>
        <div class="stats">
          <span class="stat success">Успешно: {{ result.total_success }}</span>
          <span class="stat error" v-if="result.total_failed">Ошибки: {{ result.total_failed }}</span>
        </div>
      </div>

      <table v-if="result.results && result.results.length">
        <thead>
          <tr>
            <th>Hostname</th>
            <th>IP</th>
            <th>Status</th>
            <th>File</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in result.results" :key="r.device_ip">
            <td>{{ r.hostname }}</td>
            <td>{{ r.device_ip }}</td>
            <td>
              <span class="status-badge" :class="r.success ? 'success' : 'error'">
                {{ r.success ? 'OK' : 'FAIL' }}
              </span>
            </td>
            <td><code v-if="r.file_path">{{ r.file_path }}</code></td>
            <td class="error-text">{{ r.error }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'Backup',
  data() {
    return {
      devicesInput: '',
      outputDir: '',
      loading: false,
      result: null,
      error: null,
    }
  },
  methods: {
    async runBackup() {
      this.loading = true
      this.error = null
      this.result = null

      const devices = this.devicesInput
        ? this.devicesInput.split(',').map(d => d.trim()).filter(Boolean)
        : []

      try {
        const res = await axios.post('/api/backup/run', {
          devices,
          output_dir: this.outputDir || null,
        })
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
.btn:disabled { opacity: 0.6; }

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
  justify-content: space-between;
  margin-bottom: 15px;
}

.stats {
  display: flex;
  gap: 15px;
}

.stat {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
}
.stat.success { background: #d4edda; color: #155724; }
.stat.error { background: #f8d7da; color: #721c24; }

table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px; text-align: left; border-bottom: 1px solid #eee; }
th { background: #f8f9fa; font-weight: 600; }
code { background: #f8f9fa; padding: 2px 6px; border-radius: 3px; font-family: monospace; font-size: 12px; }

.status-badge {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  color: white;
}
.status-badge.success { background: #27ae60; }
.status-badge.error { background: #e74c3c; }

.error-text { color: #c0392b; font-size: 13px; }
</style>
