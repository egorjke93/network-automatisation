<template>
  <div class="page">
    <div class="header">
      <div>
        <h1>Pipelines</h1>
        <p class="subtitle">Управление конвейерами синхронизации</p>
      </div>
      <button class="btn primary" @click="showCreateModal = true">
        + Создать Pipeline
      </button>
    </div>

    <!-- Pipeline List -->
    <div class="pipelines-grid" v-if="pipelines.length">
      <div
        v-for="p in pipelines"
        :key="p.id"
        class="pipeline-card"
        :class="{ disabled: !p.enabled }"
      >
        <div class="pipeline-header">
          <div class="pipeline-title">
            <h3>{{ p.name }}</h3>
            <span class="pipeline-id">{{ p.id }}</span>
          </div>
          <div class="pipeline-actions">
            <button class="btn-icon" title="Edit" @click="editPipeline(p)">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                <path d="M12.146.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1 0 .708l-10 10a.5.5 0 0 1-.168.11l-5 2a.5.5 0 0 1-.65-.65l2-5a.5.5 0 0 1 .11-.168l10-10zM11.207 2.5 13.5 4.793 14.793 3.5 12.5 1.207 11.207 2.5zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293l6.5-6.5zm-9.761 5.175-.106.106-1.528 3.821 3.821-1.528.106-.106A.5.5 0 0 1 5 12.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.468-.325z"/>
              </svg>
            </button>
            <button class="btn-icon danger" title="Delete" @click="confirmDelete(p)">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
              </svg>
            </button>
          </div>
        </div>

        <p class="pipeline-desc" v-if="p.description">{{ p.description }}</p>

        <div class="steps-preview">
          <div
            v-for="step in p.steps"
            :key="step.id"
            class="step-chip"
            :class="{ disabled: !step.enabled }"
          >
            <span class="step-type">{{ step.type }}</span>
            <span class="step-target">{{ step.target }}</span>
          </div>
        </div>

        <div class="pipeline-footer">
          <button
            class="btn primary small"
            @click="runPipeline(p)"
            :disabled="!p.enabled"
          >
            Run Pipeline
          </button>
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      <p>Нет pipelines. Создайте первый!</p>
    </div>

    <!-- Create/Edit Modal -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal">
        <div class="modal-header">
          <h2>{{ editingPipeline ? 'Редактировать Pipeline' : 'Создать Pipeline' }}</h2>
          <button class="btn-icon" @click="closeModal">&times;</button>
        </div>

        <form @submit.prevent="savePipeline">
          <div class="form-group">
            <label>Название *</label>
            <input v-model="form.name" type="text" required />
          </div>

          <div class="form-group">
            <label>Описание</label>
            <textarea v-model="form.description" rows="2"></textarea>
          </div>

          <div class="form-section">
            <div class="section-header">
              <h4>Шаги</h4>
              <button type="button" class="btn small" @click="addStep">+ Добавить шаг</button>
            </div>

            <div class="steps-list">
              <div
                v-for="(step, i) in form.steps"
                :key="i"
                class="step-row"
              >
                <div class="step-inputs">
                  <input
                    v-model="step.id"
                    type="text"
                    placeholder="ID шага"
                    required
                  />
                  <select v-model="step.type" @change="onTypeChange(step)" required>
                    <option value="collect">Collect</option>
                    <option value="sync">Sync</option>
                    <option value="export">Export</option>
                  </select>
                  <select v-model="step.target" required>
                    <option v-for="t in getTargetsForType(step.type)" :key="t" :value="t">{{ t }}</option>
                  </select>
                  <label class="checkbox-inline">
                    <input type="checkbox" v-model="step.enabled" />
                    On
                  </label>
                </div>
                <!-- Опции для sync шагов -->
                <div class="step-options" v-if="step.type === 'sync'">
                  <label class="checkbox-inline" v-if="['interfaces', 'ip_addresses', 'inventory', 'cables'].includes(step.target)">
                    <input type="checkbox" v-model="step.options.cleanup" />
                    Cleanup
                  </label>
                  <label class="checkbox-inline" v-if="['ip_addresses'].includes(step.target)">
                    <input type="checkbox" v-model="step.options.update_existing" />
                    Update
                  </label>
                </div>
                <button type="button" class="btn-icon danger" @click="removeStep(i)">
                  &times;
                </button>
              </div>
            </div>
          </div>

          <div v-if="formError" class="error-box">{{ formError }}</div>

          <div class="modal-footer">
            <button type="button" class="btn" @click="closeModal">Отмена</button>
            <button type="submit" class="btn primary" :disabled="saving">
              {{ saving ? 'Сохранение...' : 'Сохранить' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Run Modal -->
    <div v-if="showRunModal" class="modal-overlay" @click.self="closeRunModal">
      <div class="modal">
        <div class="modal-header">
          <h2>Запуск Pipeline: {{ runningPipeline?.name }}</h2>
          <button class="btn-icon" @click="closeRunModal">&times;</button>
        </div>

        <form @submit.prevent="executeRun" v-if="!running">
          <DeviceSelector v-model="runForm.selectedDevices" />
          <small class="hint">Если ничего не выбрано - будут использованы все устройства</small>

          <label class="checkbox highlight">
            <input type="checkbox" v-model="runForm.dryRun" />
            <span>Dry Run (только показать изменения)</span>
          </label>

          <div v-if="runError" class="error-box">{{ runError }}</div>

          <div class="modal-footer">
            <button type="button" class="btn" @click="closeRunModal">Отмена</button>
            <button type="submit" class="btn primary">
              {{ runForm.dryRun ? 'Preview' : 'Run' }}
            </button>
          </div>
        </form>

        <!-- Progress during execution -->
        <div v-if="running" class="pipeline-progress">
          <div class="progress-header-row">
            <span class="progress-label">Выполнение pipeline...</span>
            <span class="progress-time">{{ formatElapsed(runElapsed) }}</span>
          </div>
          <div class="progress-bar-container">
            <div class="progress-bar-fill" :class="{ indeterminate: runCurrentStep === -1 }"
                 :style="{ width: getProgressPercent() + '%' }"></div>
          </div>
          <div class="progress-message" v-if="runMessage">{{ runMessage }}</div>
          <div class="pipeline-steps-progress">
            <div
              v-for="(step, i) in runningPipeline.steps.filter(s => s.enabled)"
              :key="step.id"
              class="step-progress-item"
              :class="getStepProgressClass(i)"
            >
              <span class="step-icon">
                <span v-if="i < runCurrentStep">&#10003;</span>
                <span v-else-if="i === runCurrentStep" class="spinner"></span>
                <span v-else>&#9711;</span>
              </span>
              <span class="step-label">{{ step.type }}: {{ step.target }}</span>
            </div>
          </div>
        </div>

        <!-- Run Result -->
        <div v-if="runResult" class="run-result">
          <div class="result-header">
            <h3>Результат</h3>
            <span class="badge" :class="runResult.status">{{ runResult.status }}</span>
          </div>

          <div class="steps-result">
            <div
              v-for="step in runResult.steps"
              :key="step.step_id"
              class="step-result-card"
              :class="step.status"
            >
              <div class="step-header">
                <span class="step-id">{{ step.step_id }}</span>
                <span class="step-status-badge" :class="step.status">{{ step.status }}</span>
                <span class="step-duration" v-if="step.duration_ms">{{ step.duration_ms }}ms</span>
              </div>
              <!-- Step data details -->
              <div class="step-data" v-if="step.data">
                <span class="data-item created" v-if="step.data.created !== undefined">
                  <strong>+{{ step.data.created }}</strong> created
                </span>
                <span class="data-item updated" v-if="step.data.updated !== undefined">
                  <strong>~{{ step.data.updated }}</strong> updated
                </span>
                <span class="data-item deleted" v-if="step.data.deleted !== undefined">
                  <strong>-{{ step.data.deleted }}</strong> deleted
                </span>
                <span class="data-item skipped" v-if="step.data.skipped !== undefined">
                  <strong>={{ step.data.skipped }}</strong> skipped
                </span>
                <span class="data-item failed" v-if="step.data.failed">
                  <strong>!{{ step.data.failed }}</strong> failed
                </span>
                <span class="data-item info" v-if="step.data.reason">
                  {{ step.data.reason }}
                </span>
              </div>
              <!-- Detailed changes (показываем первые 5) -->
              <div class="step-details" v-if="step.data && step.data.details && hasAnyDetails(step.data.details)">
                <div class="details-section" v-if="step.data.details.create && step.data.details.create.length">
                  <div class="details-label created">Создано:</div>
                  <div class="details-list">
                    <span v-for="(item, i) in step.data.details.create.slice(0, 5)" :key="'c'+i" class="detail-item">
                      {{ item.name || item.address || JSON.stringify(item) }}
                    </span>
                    <span v-if="step.data.details.create.length > 5" class="detail-more">
                      +{{ step.data.details.create.length - 5 }} ещё
                    </span>
                  </div>
                </div>
                <div class="details-section" v-if="step.data.details.update && step.data.details.update.length">
                  <div class="details-label updated">Обновлено:</div>
                  <div class="details-list">
                    <span v-for="(item, i) in step.data.details.update.slice(0, 5)" :key="'u'+i" class="detail-item">
                      {{ item.name || item.address || JSON.stringify(item) }}
                    </span>
                    <span v-if="step.data.details.update.length > 5" class="detail-more">
                      +{{ step.data.details.update.length - 5 }} ещё
                    </span>
                  </div>
                </div>
                <div class="details-section" v-if="step.data.details.delete && step.data.details.delete.length">
                  <div class="details-label deleted">Удалено:</div>
                  <div class="details-list">
                    <span v-for="(item, i) in step.data.details.delete.slice(0, 5)" :key="'d'+i" class="detail-item">
                      {{ item.name || item.address || JSON.stringify(item) }}
                    </span>
                    <span v-if="step.data.details.delete.length > 5" class="detail-more">
                      +{{ step.data.details.delete.length - 5 }} ещё
                    </span>
                  </div>
                </div>
                <router-link v-if="!runForm.dryRun" to="/history" class="history-link">
                  Полные детали в Истории →
                </router-link>
              </div>
              <!-- Step warnings -->
              <div class="step-warnings" v-if="step.data && step.data.warnings && step.data.warnings.length">
                <div class="warning-item" v-for="(warn, i) in step.data.warnings" :key="'w'+i">
                  {{ warn }}
                </div>
              </div>
              <!-- Step errors -->
              <div class="step-errors" v-if="step.error || (step.data && step.data.errors && step.data.errors.length)">
                <div class="error-item" v-if="step.error">{{ step.error }}</div>
                <div class="error-item" v-for="(err, i) in (step.data?.errors || [])" :key="i">
                  {{ err }}
                </div>
              </div>
            </div>
          </div>

          <div class="total-duration">
            Всего: {{ runResult.total_duration_ms }}ms
          </div>
        </div>
      </div>
    </div>

    <!-- Delete Confirm Modal -->
    <div v-if="showDeleteModal" class="modal-overlay" @click.self="showDeleteModal = false">
      <div class="modal small">
        <h3>Удалить Pipeline?</h3>
        <p>Pipeline "{{ deletingPipeline?.name }}" будет удалён.</p>
        <div class="modal-footer">
          <button class="btn" @click="showDeleteModal = false">Отмена</button>
          <button class="btn danger" @click="deletePipeline" :disabled="deleting">
            {{ deleting ? 'Удаление...' : 'Удалить' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'
import DeviceSelector from '../components/DeviceSelector.vue'

export default {
  name: 'Pipelines',
  components: { DeviceSelector },
  data() {
    return {
      pipelines: [],
      loading: true,
      error: null,

      // Targets по типам
      collectTargets: ['devices', 'interfaces', 'mac', 'lldp', 'cdp', 'inventory', 'backup'],
      syncTargets: ['devices', 'interfaces', 'ip_addresses', 'inventory', 'cables', 'vlans'],
      exportTargets: ['devices', 'interfaces', 'mac', 'lldp', 'inventory'],

      // Create/Edit
      showCreateModal: false,
      editingPipeline: null,
      form: this.emptyForm(),
      formError: null,
      saving: false,

      // Run
      showRunModal: false,
      runningPipeline: null,
      runForm: {
        selectedDevices: [],
        dryRun: true,
      },
      runError: null,
      running: false,
      runResult: null,
      runTaskId: null,
      runElapsed: 0,
      runCurrentStep: -1,
      runMessage: '',
      pollTimer: null,
      elapsedTimer: null,

      // Delete
      showDeleteModal: false,
      deletingPipeline: null,
      deleting: false,
    }
  },
  async mounted() {
    await this.loadPipelines()
  },
  beforeUnmount() {
    this.stopPolling()
  },
  methods: {
    getTargetsForType(type) {
      if (type === 'collect') return this.collectTargets
      if (type === 'sync') return this.syncTargets
      if (type === 'export') return this.exportTargets
      return this.collectTargets
    },
    emptyForm() {
      return {
        name: '',
        description: '',
        steps: [
          { id: 'sync_devices', type: 'sync', target: 'devices', enabled: true, options: {}, depends_on: [] },
        ],
      }
    },
    async loadPipelines() {
      this.loading = true
      try {
        const res = await axios.get('/api/pipelines')
        this.pipelines = res.data.pipelines
      } catch (e) {
        this.error = e.response?.data?.detail || e.message
      } finally {
        this.loading = false
      }
    },

    // Create/Edit
    editPipeline(p) {
      this.editingPipeline = p
      this.form = {
        name: p.name,
        description: p.description,
        steps: p.steps.map(s => ({ ...s })),
      }
      this.formError = null
      this.showCreateModal = true
    },
    closeModal() {
      this.showCreateModal = false
      this.editingPipeline = null
      this.form = this.emptyForm()
      this.formError = null
    },
    addStep() {
      const n = this.form.steps.length + 1
      this.form.steps.push({
        id: `sync_step_${n}`,
        type: 'sync',
        target: 'devices',
        enabled: true,
        options: {},
        depends_on: [],
      })
    },
    onTypeChange(step) {
      // Сбросить target если он не подходит для нового type
      const validTargets = this.getTargetsForType(step.type)
      if (!validTargets.includes(step.target)) {
        step.target = validTargets[0]
      }
    },
    removeStep(index) {
      this.form.steps.splice(index, 1)
    },
    async savePipeline() {
      this.saving = true
      this.formError = null
      try {
        if (this.editingPipeline) {
          await axios.put(`/api/pipelines/${this.editingPipeline.id}`, this.form)
        } else {
          await axios.post('/api/pipelines', this.form)
        }
        await this.loadPipelines()
        this.closeModal()
      } catch (e) {
        const detail = e.response?.data?.detail
        if (typeof detail === 'object' && detail.errors) {
          this.formError = detail.errors.join(', ')
        } else {
          this.formError = detail || e.message
        }
      } finally {
        this.saving = false
      }
    },

    // Run
    runPipeline(p) {
      this.runningPipeline = p
      this.runForm = { selectedDevices: [], dryRun: true }
      this.runError = null
      this.runResult = null
      this.showRunModal = true
    },
    closeRunModal() {
      this.stopPolling()
      this.showRunModal = false
      this.runningPipeline = null
      this.runResult = null
      this.runTaskId = null
      this.runElapsed = 0
      this.runCurrentStep = -1
      this.runMessage = ''
    },
    async executeRun() {
      this.running = true
      this.runError = null
      this.runResult = null
      this.runTaskId = null
      this.runElapsed = 0
      this.runCurrentStep = -1
      this.runMessage = 'Запуск...'

      // Формируем devices из selectedDevices
      const devices = this.runForm.selectedDevices.map(d => ({
        host: d.host || d,
        platform: d.device_type || 'cisco_ios',
      }))

      try {
        const res = await axios.post(`/api/pipelines/${this.runningPipeline.id}/run`, {
          devices,  // Если пустой - API возьмёт все из device management
          dry_run: this.runForm.dryRun,
          async_mode: true,
        })

        // Async mode - получаем task_id и начинаем polling
        if (res.data.task_id) {
          this.runTaskId = res.data.task_id
          this.startPolling()
          this.startElapsedTimer()
        } else {
          // Sync mode - результат сразу
          this.runResult = res.data
          this.running = false
        }
      } catch (e) {
        this.runError = e.response?.data?.detail || e.message
        this.running = false
      }
    },
    startPolling() {
      this.pollTimer = setInterval(this.pollTaskStatus, 500)
    },
    stopPolling() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer)
        this.pollTimer = null
      }
      if (this.elapsedTimer) {
        clearInterval(this.elapsedTimer)
        this.elapsedTimer = null
      }
    },
    startElapsedTimer() {
      const startTime = Date.now()
      this.elapsedTimer = setInterval(() => {
        this.runElapsed = Date.now() - startTime
      }, 100)
    },
    async pollTaskStatus() {
      if (!this.runTaskId) return

      try {
        const res = await axios.get(`/api/tasks/${this.runTaskId}`)
        const task = res.data

        this.runCurrentStep = task.current_step || 0
        this.runMessage = task.message || ''
        this.runElapsed = task.elapsed_ms || this.runElapsed

        if (task.status === 'completed' || task.status === 'failed') {
          this.stopPolling()
          this.running = false

          if (task.status === 'completed' && task.result) {
            this.runResult = task.result
          } else if (task.status === 'failed') {
            this.runError = task.error || 'Pipeline failed'
          }
        }
      } catch (e) {
        console.error('Error polling task status:', e)
      }
    },
    getStepProgressClass(index) {
      if (index < this.runCurrentStep) return 'completed'
      if (index === this.runCurrentStep) return 'running'
      return 'pending'
    },
    formatElapsed(ms) {
      if (ms < 1000) return `${ms}ms`
      const seconds = Math.floor(ms / 1000)
      if (seconds < 60) return `${seconds}s`
      const minutes = Math.floor(seconds / 60)
      const secs = seconds % 60
      return `${minutes}m ${secs}s`
    },
    getProgressPercent() {
      if (!this.runningPipeline || this.runCurrentStep < 0) return 0
      const total = this.runningPipeline.steps.filter(s => s.enabled).length
      if (total === 0) return 0
      return Math.round((this.runCurrentStep / total) * 100)
    },
    hasAnyDetails(details) {
      if (!details) return false
      return (details.create && details.create.length > 0) ||
             (details.update && details.update.length > 0) ||
             (details.delete && details.delete.length > 0)
    },

    // Delete
    confirmDelete(p) {
      this.deletingPipeline = p
      this.showDeleteModal = true
    },
    async deletePipeline() {
      this.deleting = true
      try {
        await axios.delete(`/api/pipelines/${this.deletingPipeline.id}`)
        await this.loadPipelines()
        this.showDeleteModal = false
        this.deletingPipeline = null
      } catch (e) {
        alert(e.response?.data?.detail || e.message)
      } finally {
        this.deleting = false
      }
    },
  },
}
</script>

<style scoped>
.page h1 { margin-bottom: 5px; }
.subtitle { color: #666; }

.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 25px;
}

.pipelines-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 20px;
}

.pipeline-card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  padding: 20px;
  transition: box-shadow 0.2s;
}

.pipeline-card:hover {
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
}

.pipeline-card.disabled {
  opacity: 0.6;
}

.pipeline-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 10px;
}

.pipeline-title h3 {
  margin: 0 0 5px;
  font-size: 18px;
}

.pipeline-id {
  font-size: 12px;
  color: #888;
  font-family: monospace;
}

.pipeline-actions {
  display: flex;
  gap: 5px;
}

.pipeline-desc {
  color: #666;
  font-size: 14px;
  margin-bottom: 15px;
}

.steps-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 15px;
}

.step-chip {
  display: flex;
  gap: 5px;
  padding: 4px 10px;
  background: #f0f0f0;
  border-radius: 20px;
  font-size: 12px;
}

.step-chip.disabled {
  opacity: 0.5;
  text-decoration: line-through;
}

.step-type {
  color: #3498db;
  font-weight: 500;
}

.step-target {
  color: #666;
}

.pipeline-footer {
  padding-top: 15px;
  border-top: 1px solid #eee;
}

.empty-state {
  text-align: center;
  padding: 50px;
  color: #888;
}

/* Buttons */
.btn {
  padding: 10px 20px;
  border: 1px solid #ddd;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}
.btn.primary { background: #3498db; color: white; border-color: #3498db; }
.btn.danger { background: #e74c3c; color: white; border-color: #e74c3c; }
.btn.small { padding: 6px 12px; font-size: 12px; }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }

.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  padding: 5px;
  color: #666;
  border-radius: 4px;
}
.btn-icon:hover { background: #f0f0f0; }
.btn-icon.danger:hover { background: #f8d7da; color: #c0392b; }

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 8px;
  width: 100%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
  padding: 25px;
}

.modal.small { max-width: 400px; }

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.modal-header h2 { margin: 0; font-size: 20px; }

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
  padding-top: 15px;
  border-top: 1px solid #eee;
}

/* Form */
.form-group { margin-bottom: 15px; }
.form-group label { display: block; margin-bottom: 5px; font-weight: 500; }
.form-group input,
.form-group textarea,
.form-group select {
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

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.section-header h4 { margin: 0; }

.steps-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.step-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  padding: 10px;
  background: white;
  border-radius: 4px;
  margin-bottom: 5px;
}

.step-inputs {
  display: flex;
  gap: 10px;
  flex: 1;
}

.step-options {
  display: flex;
  gap: 15px;
  font-size: 12px;
  padding-left: 10px;
  border-left: 2px solid #ddd;
}

.hint {
  color: #888;
  font-size: 12px;
  margin-top: 5px;
  display: block;
}

.step-inputs input,
.step-inputs select {
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.step-inputs input { flex: 1; }
.step-inputs select { width: 100px; }

.checkbox-inline {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  white-space: nowrap;
}

.checkbox-inline input { width: 16px; height: 16px; }

.checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.checkbox input { width: 16px; height: 16px; }

.checkbox.highlight {
  background: #fff3cd;
  padding: 10px 15px;
  border-radius: 4px;
  margin: 15px 0;
}

.error-box {
  background: #f8d7da;
  color: #721c24;
  padding: 12px;
  border-radius: 4px;
  margin-top: 15px;
}

/* Run Result */
.run-result {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #eee;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 15px;
}

.result-header h3 { margin: 0; }

.badge {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  text-transform: uppercase;
}

.badge.completed { background: #d4edda; color: #155724; }
.badge.failed { background: #f8d7da; color: #721c24; }
.badge.running { background: #cce5ff; color: #004085; }

.steps-result {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.step-result-card {
  padding: 12px;
  border-radius: 6px;
  font-size: 14px;
  border-left: 4px solid #ddd;
  background: #f8f9fa;
}

.step-result-card.completed { border-left-color: #28a745; background: #f0fff4; }
.step-result-card.failed { border-left-color: #dc3545; background: #fff5f5; }
.step-result-card.skipped { border-left-color: #6c757d; background: #f8f9fa; }
.step-result-card.pending { border-left-color: #ffc107; background: #fffdf0; }

.step-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.step-id { font-weight: 600; color: #333; }

.step-status-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  text-transform: uppercase;
  font-weight: 500;
}
.step-status-badge.completed { background: #d4edda; color: #155724; }
.step-status-badge.failed { background: #f8d7da; color: #721c24; }
.step-status-badge.skipped { background: #e2e3e5; color: #495057; }
.step-status-badge.pending { background: #fff3cd; color: #856404; }

.step-duration { font-size: 12px; color: #888; margin-left: auto; }

.step-data {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 6px;
}

.data-item {
  font-size: 13px;
  padding: 3px 8px;
  border-radius: 4px;
  background: #fff;
}
.data-item.created { color: #28a745; }
.data-item.updated { color: #007bff; }
.data-item.deleted { color: #fd7e14; }
.data-item.skipped { color: #6c757d; }
.data-item.failed { color: #dc3545; }
.data-item.info { color: #666; font-style: italic; }

.step-warnings {
  margin-top: 8px;
  padding: 8px;
  background: #fff3cd;
  border-radius: 4px;
}

.warning-item {
  color: #856404;
  font-size: 12px;
  margin-bottom: 4px;
}
.warning-item:last-child { margin-bottom: 0; }

.step-errors {
  margin-top: 8px;
  padding: 8px;
  background: #f8d7da;
  border-radius: 4px;
}

.error-item {
  color: #721c24;
  font-size: 12px;
  margin-bottom: 4px;
}
.error-item:last-child { margin-bottom: 0; }

/* Step Details */
.step-details {
  margin-top: 10px;
  padding: 10px;
  background: #fff;
  border-radius: 4px;
  border: 1px solid #e9ecef;
}

.details-section {
  margin-bottom: 8px;
}
.details-section:last-child { margin-bottom: 0; }

.details-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  margin-bottom: 4px;
}
.details-label.created { color: #28a745; }
.details-label.updated { color: #007bff; }
.details-label.deleted { color: #dc3545; }
.details-label.skipped { color: #6c757d; }

.details-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.detail-item {
  font-size: 12px;
  padding: 3px 8px;
  background: #f8f9fa;
  border-radius: 3px;
  color: #495057;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Pipeline Progress */
.pipeline-progress {
  padding: 15px 0;
}

.progress-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.progress-label {
  font-weight: 500;
  color: #333;
}

.progress-time {
  font-size: 13px;
  color: #666;
  font-family: monospace;
}

.progress-bar-container {
  height: 8px;
  background: #e9ecef;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 15px;
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #3498db, #2ecc71);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-bar-fill.indeterminate {
  width: 30% !important;
  animation: indeterminate 1.5s ease-in-out infinite;
}

@keyframes indeterminate {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(400%); }
}

.progress-message {
  font-size: 13px;
  color: #666;
  margin-bottom: 12px;
  padding: 6px 10px;
  background: #f8f9fa;
  border-radius: 4px;
  font-family: monospace;
}

.pipeline-steps-progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.step-progress-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  background: #f8f9fa;
  transition: all 0.2s;
}

.step-progress-item.pending {
  color: #6c757d;
}

.step-progress-item.running {
  background: #e7f1ff;
  color: #0d6efd;
  font-weight: 500;
}

.step-progress-item.completed {
  background: #d1e7dd;
  color: #198754;
}

.step-icon {
  width: 20px;
  text-align: center;
  font-size: 12px;
}

.step-icon .spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid #0d6efd;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.step-label {
  flex: 1;
}

.total-duration {
  margin-top: 15px;
  text-align: right;
  font-size: 14px;
  color: #666;
}
</style>
