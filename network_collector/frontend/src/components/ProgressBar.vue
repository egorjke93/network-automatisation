<template>
  <div class="progress-container" v-if="visible">
    <div class="progress-header">
      <span class="progress-status" :class="statusClass">{{ statusLabel }}</span>
      <span class="progress-percent">{{ progress }}%</span>
    </div>

    <div class="progress-bar">
      <div class="progress-fill" :style="{ width: progress + '%' }" :class="statusClass"></div>
    </div>

    <div class="progress-details">
      <span class="progress-message">{{ message }}</span>
      <span class="progress-time" v-if="elapsedMs > 0">{{ formatDuration(elapsedMs) }}</span>
    </div>

    <div class="progress-steps" v-if="steps.length > 0">
      <div
        v-for="(step, i) in steps"
        :key="i"
        class="step"
        :class="step.status"
      >
        <span class="step-indicator">
          <span v-if="step.status === 'completed'" class="icon-check">&#10003;</span>
          <span v-else-if="step.status === 'running'" class="icon-spinner"></span>
          <span v-else class="icon-pending">&#9711;</span>
        </span>
        <span class="step-name">{{ step.name }}</span>
        <span class="step-progress" v-if="step.status === 'running' && step.total > 0">
          {{ step.current }}/{{ step.total }}
        </span>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'ProgressBar',
  props: {
    taskId: {
      type: String,
      default: null,
    },
    pollInterval: {
      type: Number,
      default: 500, // 500ms
    },
    autoHide: {
      type: Boolean,
      default: true,
    },
    hideDelay: {
      type: Number,
      default: 3000, // Hide after 3 seconds
    },
  },
  data() {
    return {
      visible: false,
      status: 'pending',
      progress: 0,
      message: '',
      elapsedMs: 0,
      steps: [],
      pollTimer: null,
      hideTimer: null,
    }
  },
  computed: {
    statusClass() {
      return {
        pending: 'status-pending',
        running: 'status-running',
        completed: 'status-completed',
        failed: 'status-failed',
      }[this.status] || 'status-pending'
    },
    statusLabel() {
      return {
        pending: 'Ожидание...',
        running: 'Выполнение...',
        completed: 'Завершено',
        failed: 'Ошибка',
      }[this.status] || this.status
    },
  },
  watch: {
    taskId: {
      immediate: true,
      handler(newId) {
        if (newId) {
          this.startPolling()
        } else {
          this.stopPolling()
        }
      },
    },
  },
  methods: {
    async startPolling() {
      this.visible = true
      this.status = 'running'
      this.progress = 0
      this.message = 'Запуск...'
      this.steps = []
      this.clearHideTimer()

      await this.fetchTaskStatus()

      if (this.status === 'running' || this.status === 'pending') {
        this.pollTimer = setInterval(this.fetchTaskStatus, this.pollInterval)
      }
    },

    stopPolling() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer)
        this.pollTimer = null
      }
    },

    clearHideTimer() {
      if (this.hideTimer) {
        clearTimeout(this.hideTimer)
        this.hideTimer = null
      }
    },

    async fetchTaskStatus() {
      if (!this.taskId) return

      try {
        const res = await axios.get(`/api/tasks/${this.taskId}`)
        const task = res.data

        this.status = task.status
        this.progress = task.progress_percent || 0
        this.message = task.message || ''
        this.elapsedMs = task.elapsed_ms || 0
        this.steps = task.steps || []

        if (task.status === 'completed' || task.status === 'failed') {
          this.stopPolling()
          this.$emit('complete', task)

          if (this.autoHide) {
            this.hideTimer = setTimeout(() => {
              this.visible = false
            }, this.hideDelay)
          }
        }
      } catch (e) {
        console.error('Error fetching task status:', e)
        this.stopPolling()
      }
    },

    formatDuration(ms) {
      if (ms < 1000) return `${ms}ms`
      const seconds = Math.floor(ms / 1000)
      if (seconds < 60) return `${seconds}s`
      const minutes = Math.floor(seconds / 60)
      const secs = seconds % 60
      return `${minutes}m ${secs}s`
    },
  },
  beforeUnmount() {
    this.stopPolling()
    this.clearHideTimer()
  },
}
</script>

<style scoped>
.progress-container {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  padding: 16px;
  margin-bottom: 20px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.progress-status {
  font-weight: 500;
  font-size: 14px;
}

.progress-status.status-pending { color: #6c757d; }
.progress-status.status-running { color: #0d6efd; }
.progress-status.status-completed { color: #198754; }
.progress-status.status-failed { color: #dc3545; }

.progress-percent {
  font-weight: 600;
  font-size: 14px;
  color: #333;
}

.progress-bar {
  height: 8px;
  background: #e9ecef;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 8px;
}

.progress-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-fill.status-pending { background: #6c757d; }
.progress-fill.status-running { background: linear-gradient(90deg, #0d6efd, #0dcaf0); }
.progress-fill.status-completed { background: #198754; }
.progress-fill.status-failed { background: #dc3545; }

.progress-details {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: #666;
}

.progress-message {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-time {
  margin-left: 10px;
  color: #888;
}

/* Steps */
.progress-steps {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #eee;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.step {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 16px;
  font-size: 12px;
  background: #f8f9fa;
}

.step.pending { color: #6c757d; }
.step.running {
  color: #0d6efd;
  background: #e7f1ff;
}
.step.completed {
  color: #198754;
  background: #d1e7dd;
}
.step.failed {
  color: #dc3545;
  background: #f8d7da;
}

.step-indicator {
  font-size: 10px;
}

.icon-check { color: #198754; }
.icon-pending { color: #adb5bd; }

.icon-spinner {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 2px solid #0d6efd;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.step-name {
  font-weight: 500;
}

.step-progress {
  color: #666;
  font-size: 11px;
}
</style>
