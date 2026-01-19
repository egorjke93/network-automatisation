<template>
  <div class="page">
    <h1>Backup</h1>
    <p class="subtitle">Резервное копирование конфигураций</p>

    <div class="form-card">
      <form @submit.prevent="runBackup">
        <DeviceSelector v-model="selectedDevices" />
        <button type="submit" class="btn primary" :disabled="loading">
          {{ loading ? 'Загрузка...' : 'Запустить Backup' }}
        </button>
      </form>
    </div>

    <ProgressBar :task-id="taskId" @complete="onTaskComplete" />

    <div v-if="error" class="error-box">{{ error }}</div>

    <div v-if="result" class="result">
      <div class="result-header">
        <h3>Результат</h3>
        <div class="stats">
          <span class="stat success">Успешно: {{ result.total_success }}</span>
          <span class="stat error" v-if="result.total_failed">Ошибки: {{ result.total_failed }}</span>
        </div>
        <button
          v-if="result.total_success > 0"
          class="btn download"
          @click="downloadZip"
          :disabled="downloading"
        >
          {{ downloading ? 'Скачивание...' : 'Скачать ZIP' }}
        </button>
      </div>

      <table v-if="result.results && result.results.length">
        <thead>
          <tr>
            <th>Hostname</th>
            <th>IP</th>
            <th>Status</th>
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
            <td class="error-text">{{ r.error }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script>
import axios from 'axios'
import ProgressBar from '../components/ProgressBar.vue'
import DeviceSelector from '../components/DeviceSelector.vue'

export default {
  name: 'Backup',
  components: { ProgressBar, DeviceSelector },
  data() {
    return {
      selectedDevices: [],
      loading: false,
      downloading: false,
      result: null,
      error: null,
      taskId: null,
    }
  },
  methods: {
    async runBackup() {
      this.loading = true
      this.error = null
      this.result = null
      this.taskId = null

      try {
        const res = await axios.post('/api/backup/run', {
          devices: this.selectedDevices,
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
        const results = task.result.data.map((r) => ({
          hostname: r.hostname || '',
          device_ip: r.device_ip || '',
          success: r.success || false,
          error: r.error || '',
        }))
        this.result = {
          success: true,
          total_success: task.result.success || results.filter((r) => r.success).length,
          total_failed: task.result.failed || results.filter((r) => !r.success).length,
          results,
        }
      } else if (task.status === 'failed') {
        this.error = task.error || 'Ошибка backup'
      }
    },
    async downloadZip() {
      if (!this.taskId) return
      this.downloading = true
      try {
        const response = await axios.get(`/api/backup/download/${this.taskId}`, {
          responseType: 'blob',
        })
        // Получаем имя файла из заголовка Content-Disposition или используем дефолтное
        const contentDisposition = response.headers['content-disposition']
        let filename = 'backup.zip'
        if (contentDisposition) {
          const match = contentDisposition.match(/filename=(.+)/)
          if (match) filename = match[1]
        }
        // Создаём ссылку для скачивания
        const url = window.URL.createObjectURL(new Blob([response.data]))
        const link = document.createElement('a')
        link.href = url
        link.setAttribute('download', filename)
        document.body.appendChild(link)
        link.click()
        link.remove()
        window.URL.revokeObjectURL(url)
      } catch (e) {
        this.error = 'Ошибка скачивания: ' + (e.response?.data?.detail || e.message)
      } finally {
        this.downloading = false
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
.btn.download { background: #27ae60; color: white; margin-left: auto; }
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
