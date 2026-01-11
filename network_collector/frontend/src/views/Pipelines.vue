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
                  <select v-model="step.type" required>
                    <option value="collect">Collect</option>
                    <option value="sync">Sync</option>
                    <option value="export">Export</option>
                  </select>
                  <select v-model="step.target" required>
                    <option value="devices">devices</option>
                    <option value="interfaces">interfaces</option>
                    <option value="mac">mac</option>
                    <option value="lldp">lldp</option>
                    <option value="inventory">inventory</option>
                    <option value="cables">cables</option>
                    <option value="vlans">vlans</option>
                    <option value="backup">backup</option>
                  </select>
                  <label class="checkbox-inline">
                    <input type="checkbox" v-model="step.enabled" />
                    On
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

        <form @submit.prevent="executeRun">
          <div class="form-group">
            <label>Устройства (IP через запятую) *</label>
            <input
              v-model="runForm.devicesInput"
              type="text"
              placeholder="10.0.0.1, 10.0.0.2"
              required
            />
          </div>

          <label class="checkbox highlight">
            <input type="checkbox" v-model="runForm.dryRun" />
            <span>Dry Run (только показать изменения)</span>
          </label>

          <div v-if="runError" class="error-box">{{ runError }}</div>

          <div class="modal-footer">
            <button type="button" class="btn" @click="closeRunModal">Отмена</button>
            <button type="submit" class="btn primary" :disabled="running">
              {{ running ? 'Выполнение...' : (runForm.dryRun ? 'Preview' : 'Run') }}
            </button>
          </div>
        </form>

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
              class="step-result"
              :class="step.status"
            >
              <span class="step-id">{{ step.step_id }}</span>
              <span class="step-status">{{ step.status }}</span>
              <span class="step-duration" v-if="step.duration_ms">{{ step.duration_ms }}ms</span>
              <span class="step-error" v-if="step.error">{{ step.error }}</span>
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

export default {
  name: 'Pipelines',
  data() {
    return {
      pipelines: [],
      loading: true,
      error: null,

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
        devicesInput: '',
        dryRun: true,
      },
      runError: null,
      running: false,
      runResult: null,

      // Delete
      showDeleteModal: false,
      deletingPipeline: null,
      deleting: false,
    }
  },
  async mounted() {
    await this.loadPipelines()
  },
  methods: {
    emptyForm() {
      return {
        name: '',
        description: '',
        steps: [
          { id: 'collect_devices', type: 'collect', target: 'devices', enabled: true, options: {}, depends_on: [] },
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
        id: `step_${n}`,
        type: 'collect',
        target: 'devices',
        enabled: true,
        options: {},
        depends_on: [],
      })
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
      this.runForm = { devicesInput: '', dryRun: true }
      this.runError = null
      this.runResult = null
      this.showRunModal = true
    },
    closeRunModal() {
      this.showRunModal = false
      this.runningPipeline = null
      this.runResult = null
    },
    async executeRun() {
      this.running = true
      this.runError = null
      this.runResult = null

      const devices = this.runForm.devicesInput
        .split(',')
        .map(d => d.trim())
        .filter(Boolean)
        .map(ip => ({ host: ip, platform: 'cisco_ios' }))

      try {
        const res = await axios.post(`/api/pipelines/${this.runningPipeline.id}/run`, {
          devices,
          dry_run: this.runForm.dryRun,
        })
        this.runResult = res.data
      } catch (e) {
        this.runError = e.response?.data?.detail || e.message
      } finally {
        this.running = false
      }
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
  gap: 10px;
  align-items: center;
}

.step-inputs {
  display: flex;
  gap: 10px;
  flex: 1;
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
  gap: 8px;
}

.step-result {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 4px;
  font-size: 14px;
}

.step-result.completed { background: #d4edda; }
.step-result.failed { background: #f8d7da; }
.step-result.skipped { background: #e2e3e5; }
.step-result.pending { background: #f8f9fa; }

.step-id { font-weight: 500; }
.step-status { font-size: 12px; color: #666; }
.step-duration { font-size: 12px; color: #888; margin-left: auto; }
.step-error { color: #721c24; font-size: 12px; }

.total-duration {
  margin-top: 15px;
  text-align: right;
  font-size: 14px;
  color: #666;
}
</style>
