<template>
  <div class="device-selector">
    <div class="selector-header">
      <label>Устройства</label>
      <button type="button" class="btn-toggle" @click="toggleMode">
        {{ mode === 'select' ? 'Ввод вручную' : 'Выбрать из списка' }}
      </button>
    </div>

    <!-- Manual input mode -->
    <div v-if="mode === 'manual'" class="manual-input">
      <input
        v-model="manualInput"
        type="text"
        :placeholder="placeholder"
        @input="onManualInput"
      />
      <small class="hint">IP через запятую, пусто = все enabled устройства</small>
    </div>

    <!-- Select from list mode -->
    <div v-else class="select-mode">
      <div class="select-toolbar">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Поиск..."
          class="search-input"
        />
        <div class="select-actions">
          <button type="button" class="btn-small" @click="selectAll">Все</button>
          <button type="button" class="btn-small" @click="selectNone">Очистить</button>
        </div>
      </div>

      <div class="devices-list" v-if="!loadingDevices">
        <label
          v-for="device in filteredDevices"
          :key="device.host"
          class="device-item"
          :class="{ disabled: !device.enabled }"
        >
          <input
            type="checkbox"
            :value="device.host"
            v-model="selectedDevices"
            :disabled="!device.enabled"
          />
          <span class="device-host">{{ device.host }}</span>
          <span class="device-name" v-if="device.name">{{ device.name }}</span>
          <span class="device-type">{{ device.device_type }}</span>
        </label>
        <div v-if="filteredDevices.length === 0" class="no-devices">
          {{ searchQuery ? 'Ничего не найдено' : 'Нет устройств' }}
        </div>
      </div>
      <div v-else class="loading">Загрузка...</div>

      <div class="selected-count" v-if="selectedDevices.length > 0">
        Выбрано: {{ selectedDevices.length }}
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'DeviceSelector',
  props: {
    modelValue: {
      type: Array,
      default: () => [],
    },
    placeholder: {
      type: String,
      default: '10.0.0.1, 10.0.0.2',
    },
  },
  emits: ['update:modelValue'],
  data() {
    return {
      mode: 'manual', // 'manual' or 'select'
      manualInput: '',
      searchQuery: '',
      devices: [],
      selectedDevices: [],
      loadingDevices: false,
    }
  },
  computed: {
    filteredDevices() {
      if (!this.searchQuery) return this.devices
      const q = this.searchQuery.toLowerCase()
      return this.devices.filter(d =>
        d.host.toLowerCase().includes(q) ||
        (d.name && d.name.toLowerCase().includes(q)) ||
        (d.device_type && d.device_type.toLowerCase().includes(q))
      )
    },
  },
  watch: {
    selectedDevices: {
      handler(val) {
        if (this.mode === 'select') {
          this.$emit('update:modelValue', val)
        }
      },
      deep: true,
    },
    modelValue: {
      immediate: true,
      handler(val) {
        if (Array.isArray(val)) {
          this.selectedDevices = [...val]
          this.manualInput = val.join(', ')
        }
      },
    },
  },
  methods: {
    toggleMode() {
      if (this.mode === 'manual') {
        this.mode = 'select'
        this.loadDevices()
      } else {
        this.mode = 'manual'
      }
    },
    async loadDevices() {
      this.loadingDevices = true
      try {
        const res = await axios.get('/api/devices')
        this.devices = res.data.devices || []
      } catch (e) {
        console.error('Failed to load devices:', e)
        this.devices = []
      }
      this.loadingDevices = false
    },
    onManualInput() {
      const devices = this.manualInput
        .split(',')
        .map(d => d.trim())
        .filter(Boolean)
      this.$emit('update:modelValue', devices)
    },
    selectAll() {
      this.selectedDevices = this.filteredDevices
        .filter(d => d.enabled)
        .map(d => d.host)
    },
    selectNone() {
      this.selectedDevices = []
    },
  },
}
</script>

<style scoped>
.device-selector {
  margin-bottom: 15px;
}

.selector-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.selector-header label {
  font-weight: 500;
}

.btn-toggle {
  padding: 4px 10px;
  border: 1px solid #3498db;
  background: white;
  color: #3498db;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.btn-toggle:hover {
  background: #3498db;
  color: white;
}

.manual-input input {
  width: 100%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.hint {
  display: block;
  margin-top: 4px;
  color: #888;
  font-size: 12px;
}

.select-mode {
  border: 1px solid #ddd;
  border-radius: 4px;
  overflow: hidden;
}

.select-toolbar {
  display: flex;
  gap: 10px;
  padding: 10px;
  background: #f8f9fa;
  border-bottom: 1px solid #eee;
}

.search-input {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
}

.select-actions {
  display: flex;
  gap: 5px;
}

.btn-small {
  padding: 4px 10px;
  border: 1px solid #ddd;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.btn-small:hover {
  background: #f0f0f0;
}

.devices-list {
  max-height: 250px;
  overflow-y: auto;
}

.device-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  cursor: pointer;
  border-bottom: 1px solid #eee;
}

.device-item:hover {
  background: #f8f9fa;
}

.device-item.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.device-item input[type="checkbox"] {
  margin: 0;
}

.device-host {
  font-family: monospace;
  font-weight: 500;
  min-width: 120px;
}

.device-name {
  color: #666;
  flex: 1;
}

.device-type {
  font-size: 11px;
  padding: 2px 6px;
  background: #e9ecef;
  border-radius: 3px;
  color: #555;
}

.no-devices {
  padding: 20px;
  text-align: center;
  color: #888;
}

.loading {
  padding: 20px;
  text-align: center;
  color: #666;
}

.selected-count {
  padding: 8px 12px;
  background: #e3f2fd;
  color: #1565c0;
  font-size: 13px;
  font-weight: 500;
}
</style>
