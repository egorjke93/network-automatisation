<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1>Управление устройствами</h1>
        <p class="subtitle">Добавление, редактирование и удаление устройств</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-netbox" @click="openNetboxImportModal" :disabled="loading">
          📥 Импорт из NetBox
        </button>
        <button class="btn btn-secondary" @click="openFileImportModal" :disabled="loading">
          📁 Импорт из файла
        </button>
        <button class="btn btn-primary" @click="openAddModal">
          + Добавить устройство
        </button>
      </div>
    </div>

    <!-- Stats Cards -->
    <div class="stats-row" v-if="stats">
      <div class="stat-card">
        <div class="stat-value">{{ stats.total }}</div>
        <div class="stat-label">Всего устройств</div>
      </div>
      <div class="stat-card success">
        <div class="stat-value">{{ stats.enabled }}</div>
        <div class="stat-label">Активных</div>
      </div>
      <div class="stat-card warning">
        <div class="stat-value">{{ stats.disabled }}</div>
        <div class="stat-label">Отключено</div>
      </div>
    </div>

    <!-- Filters -->
    <div class="filters">
      <input
        v-model="searchQuery"
        type="text"
        placeholder="Поиск по host, name, site..."
        class="search-input"
      />
      <select v-model="filterType" @change="loadDevices">
        <option value="">Все платформы</option>
        <option v-for="t in deviceTypes" :key="t.value" :value="t.value">
          {{ t.label }}
        </option>
      </select>
      <select v-model="filterSite">
        <option value="">Все сайты</option>
        <option v-for="site in sites" :key="site" :value="site">
          {{ site }}
        </option>
      </select>
      <select v-model="filterRole">
        <option value="">Все роли</option>
        <option v-for="role in roles" :key="role" :value="role">
          {{ getRoleLabel(role) }}
        </option>
      </select>
      <select v-model="filterEnabled">
        <option value="">Все</option>
        <option value="true">Активные</option>
        <option value="false">Отключённые</option>
      </select>
      <button class="btn btn-light" @click="loadDevices" :disabled="loading">
        Обновить
      </button>
    </div>

    <!-- Devices Table -->
    <div class="table-container" v-if="filteredDevices.length">
      <table class="devices-table">
        <thead>
          <tr>
            <th class="sortable" @click="sortBy('enabled')">
              Статус
              <span v-if="sortField === 'enabled'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th class="sortable" @click="sortBy('host')">
              Host
              <span v-if="sortField === 'host'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th class="sortable" @click="sortBy('name')">
              Имя
              <span v-if="sortField === 'name'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th class="sortable" @click="sortBy('device_type')">
              Платформа
              <span v-if="sortField === 'device_type'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th class="sortable" @click="sortBy('site')">
              Сайт
              <span v-if="sortField === 'site'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th class="sortable" @click="sortBy('role')">
              Роль
              <span v-if="sortField === 'role'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th>Описание</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="device in filteredDevices" :key="device.id" :class="{ disabled: !device.enabled }">
            <td>
              <label class="toggle-switch">
                <input
                  type="checkbox"
                  :checked="device.enabled"
                  @change="toggleDevice(device)"
                />
                <span class="slider"></span>
              </label>
            </td>
            <td class="host-cell">{{ device.host }}</td>
            <td>{{ device.name || '-' }}</td>
            <td>
              <span class="type-badge" :class="device.device_type">
                {{ getTypeLabel(device.device_type) }}
              </span>
            </td>
            <td>{{ device.site || '-' }}</td>
            <td>
              <span v-if="device.role" class="role-badge" :class="device.role">
                {{ getRoleLabel(device.role) }}
              </span>
              <span v-else>-</span>
            </td>
            <td class="description-cell">{{ device.description || '-' }}</td>
            <td class="actions-cell">
              <button class="btn-icon" @click="openEditModal(device)" title="Редактировать">
                &#9998;
              </button>
              <button class="btn-icon danger" @click="confirmDelete(device)" title="Удалить">
                &#128465;
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="empty-state" v-else-if="!loading">
      <p v-if="searchQuery || filterType || filterSite || filterEnabled">
        Устройства не найдены по заданным фильтрам
      </p>
      <p v-else>
        Нет устройств. Добавьте первое устройство или импортируйте из devices_ips.py
      </p>
    </div>

    <div class="loading" v-if="loading">Загрузка...</div>

    <!-- Add/Edit Modal -->
    <div class="modal-overlay" v-if="showModal" @click.self="closeModal">
      <div class="modal">
        <div class="modal-header">
          <h2>{{ editingDevice ? 'Редактировать устройство' : 'Добавить устройство' }}</h2>
          <button class="modal-close" @click="closeModal">&times;</button>
        </div>

        <form @submit.prevent="saveDevice" class="device-form">
          <div class="form-group">
            <label>Host (IP или hostname) *</label>
            <input
              v-model="form.host"
              type="text"
              required
              placeholder="192.168.1.1"
            />
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Платформа (SSH) *</label>
              <select v-model="form.device_type" required>
                <option v-for="t in deviceTypes" :key="t.value" :value="t.value">
                  {{ t.label }}
                </option>
              </select>
            </div>

            <div class="form-group">
              <label>Роль (NetBox)</label>
              <select v-model="form.role">
                <option value="">-- Не указана --</option>
                <option v-for="r in deviceRoles" :key="r.value" :value="r.value">
                  {{ r.label }}
                </option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Имя</label>
              <input
                v-model="form.name"
                type="text"
                placeholder="core-switch-1"
              />
            </div>

            <div class="form-group">
              <label>Сайт (NetBox)</label>
              <input
                v-model="form.site"
                type="text"
                placeholder="DC-1"
                list="sites-list"
              />
              <datalist id="sites-list">
                <option v-for="site in sites" :key="site" :value="site" />
              </datalist>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Tenant (NetBox)</label>
              <input
                v-model="form.tenant"
                type="text"
                placeholder="Company-A"
              />
            </div>

            <div class="form-group">
              <label>Теги (через запятую)</label>
              <input
                v-model="form.tagsInput"
                type="text"
                placeholder="production, core"
              />
            </div>
          </div>

          <div class="form-group">
            <label>Описание</label>
            <input
              v-model="form.description"
              type="text"
              placeholder="Core switch in DC1"
            />
          </div>

          <div class="form-group checkbox-group">
            <label class="checkbox-label">
              <input type="checkbox" v-model="form.enabled" />
              Устройство активно
            </label>
          </div>

          <div class="form-actions">
            <button type="button" class="btn btn-secondary" @click="closeModal">
              Отмена
            </button>
            <button type="submit" class="btn btn-primary" :disabled="saving">
              {{ saving ? 'Сохранение...' : (editingDevice ? 'Сохранить' : 'Добавить') }}
            </button>
          </div>

          <div v-if="formError" class="form-error">{{ formError }}</div>
        </form>
      </div>
    </div>

    <!-- NetBox Import Modal -->
    <div class="modal-overlay" v-if="showNetboxModal" @click.self="closeNetboxModal">
      <div class="modal">
        <div class="modal-header">
          <h2>📥 Импорт устройств из NetBox</h2>
          <button class="modal-close" @click="closeNetboxModal">&times;</button>
        </div>

        <form @submit.prevent="importFromNetbox" class="device-form">
          <div class="form-group">
            <label>URL NetBox *</label>
            <input
              v-model="netboxForm.url"
              type="url"
              required
              placeholder="https://netbox.example.com"
            />
          </div>

          <div class="form-group">
            <label>API Token *</label>
            <input
              v-model="netboxForm.token"
              type="password"
              required
              placeholder="API токен из NetBox"
            />
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Сайт (фильтр)</label>
              <input
                v-model="netboxForm.site"
                type="text"
                placeholder="DC-1 (опционально)"
              />
            </div>

            <div class="form-group">
              <label>Роль (фильтр)</label>
              <input
                v-model="netboxForm.role"
                type="text"
                placeholder="switch (опционально)"
              />
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Статус</label>
              <select v-model="netboxForm.status">
                <option value="active">Активные</option>
                <option value="planned">Запланированные</option>
                <option value="staged">Staged</option>
                <option value="">Все</option>
              </select>
            </div>

            <div class="form-group checkbox-group">
              <label class="checkbox-label">
                <input type="checkbox" v-model="netboxForm.replace" />
                Заменить все существующие устройства
              </label>
            </div>
          </div>

          <!-- Progress Bar -->
          <div v-if="netboxImporting" class="progress-container">
            <div class="progress-bar">
              <div class="progress-bar-fill" :style="{ width: netboxProgress + '%' }"></div>
            </div>
            <div class="progress-text">{{ netboxProgressText }}</div>
          </div>

          <!-- Result -->
          <div v-if="netboxResult" :class="['import-result', netboxResult.success ? 'success' : 'error']">
            <p><strong>{{ netboxResult.message }}</strong></p>
            <p v-if="netboxResult.fetched">Получено из NetBox: {{ netboxResult.fetched }}</p>
            <p v-if="netboxResult.added">Добавлено: {{ netboxResult.added }}</p>
            <p v-if="netboxResult.skipped">Пропущено: {{ netboxResult.skipped }}</p>
            <p v-if="netboxResult.errors">Ошибок: {{ netboxResult.errors }}</p>
          </div>

          <div v-if="netboxError" class="form-error">{{ netboxError }}</div>

          <div class="form-actions">
            <button type="button" class="btn btn-secondary" @click="closeNetboxModal">
              Закрыть
            </button>
            <button type="submit" class="btn btn-netbox" :disabled="netboxImporting">
              {{ netboxImporting ? 'Импорт...' : 'Импортировать' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- File Import Modal -->
    <div class="modal-overlay" v-if="showFileImportModal" @click.self="closeFileImportModal">
      <div class="modal">
        <div class="modal-header">
          <h2>📁 Импорт устройств из файла</h2>
          <button class="modal-close" @click="closeFileImportModal">&times;</button>
        </div>

        <form @submit.prevent="importFromFile" class="device-form">
          <div class="form-group">
            <label>Выберите файл *</label>
            <input
              type="file"
              ref="fileInput"
              @change="onFileSelected"
              accept=".json,.xlsx,.xls,.csv,.py"
              class="file-input"
            />
            <p class="hint">Поддерживаемые форматы: JSON, Excel (.xlsx), CSV, Python (.py)</p>
          </div>

          <div v-if="selectedFile" class="selected-file">
            <span class="file-name">📄 {{ selectedFile.name }}</span>
            <span class="file-size">({{ formatFileSize(selectedFile.size) }})</span>
          </div>

          <div class="form-group checkbox-group">
            <label class="checkbox-label">
              <input type="checkbox" v-model="fileImportReplace" />
              Заменить все существующие устройства
            </label>
          </div>

          <!-- Progress Bar -->
          <div v-if="fileImporting" class="progress-container">
            <div class="progress-bar">
              <div class="progress-bar-fill" :style="{ width: fileImportProgress + '%' }"></div>
            </div>
            <div class="progress-text">{{ fileImportProgressText }}</div>
          </div>

          <!-- Result -->
          <div v-if="fileImportResult" :class="['import-result', fileImportResult.success ? 'success' : 'error']">
            <p><strong>{{ fileImportResult.message }}</strong></p>
            <p v-if="fileImportResult.added">Добавлено: {{ fileImportResult.added }}</p>
            <p v-if="fileImportResult.skipped">Пропущено: {{ fileImportResult.skipped }}</p>
            <p v-if="fileImportResult.errors">Ошибок: {{ fileImportResult.errors }}</p>
          </div>

          <div v-if="fileImportError" class="form-error">{{ fileImportError }}</div>

          <div class="form-actions">
            <button type="button" class="btn btn-secondary" @click="closeFileImportModal">
              Закрыть
            </button>
            <button type="submit" class="btn btn-primary" :disabled="fileImporting || !selectedFile">
              {{ fileImporting ? 'Импорт...' : 'Импортировать' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Delete Confirmation Modal -->
    <div class="modal-overlay" v-if="showDeleteModal" @click.self="showDeleteModal = false">
      <div class="modal modal-small">
        <div class="modal-header">
          <h2>Подтверждение удаления</h2>
        </div>
        <div class="modal-body">
          <p>Удалить устройство <strong>{{ deviceToDelete?.host }}</strong>?</p>
          <p class="warning-text">Это действие нельзя отменить.</p>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showDeleteModal = false">
            Отмена
          </button>
          <button class="btn btn-danger" @click="deleteDevice" :disabled="deleting">
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
  name: 'DeviceManagement',
  data() {
    return {
      devices: [],
      stats: null,
      deviceTypes: [],
      deviceRoles: [],
      loading: false,
      saving: false,
      deleting: false,

      // Filters
      searchQuery: '',
      filterType: '',
      filterSite: '',
      filterRole: '',
      filterEnabled: '',

      // Sorting
      sortField: 'host',
      sortDir: 'asc',

      // Modals
      showModal: false,
      showDeleteModal: false,
      showNetboxModal: false,
      showFileImportModal: false,
      editingDevice: null,
      deviceToDelete: null,

      // File Import
      selectedFile: null,
      fileImportReplace: false,
      fileImporting: false,
      fileImportProgress: 0,
      fileImportProgressText: '',
      fileImportResult: null,
      fileImportError: '',

      // NetBox Import
      netboxForm: {
        url: '',
        token: '',
        site: '',
        role: '',
        status: 'active',
        replace: false,
      },
      netboxImporting: false,
      netboxProgress: 0,
      netboxProgressText: '',
      netboxResult: null,
      netboxError: '',

      // Form
      form: {
        host: '',
        device_type: 'cisco_ios',
        name: '',
        site: '',
        role: '',
        tenant: '',
        description: '',
        enabled: true,
        tagsInput: '',
      },
      formError: '',
    }
  },
  computed: {
    sites() {
      const siteSet = new Set()
      this.devices.forEach(d => {
        if (d.site) siteSet.add(d.site)
      })
      return Array.from(siteSet).sort()
    },
    roles() {
      const roleSet = new Set()
      this.devices.forEach(d => {
        if (d.role) roleSet.add(d.role)
      })
      return Array.from(roleSet).sort()
    },
    filteredDevices() {
      let result = [...this.devices]

      // Filter by search
      if (this.searchQuery) {
        const q = this.searchQuery.toLowerCase()
        result = result.filter(d =>
          d.host?.toLowerCase().includes(q) ||
          d.name?.toLowerCase().includes(q) ||
          d.site?.toLowerCase().includes(q) ||
          d.role?.toLowerCase().includes(q) ||
          d.description?.toLowerCase().includes(q)
        )
      }

      // Filter by type
      if (this.filterType) {
        result = result.filter(d => d.device_type === this.filterType)
      }

      // Filter by site
      if (this.filterSite) {
        result = result.filter(d => d.site === this.filterSite)
      }

      // Filter by role
      if (this.filterRole) {
        result = result.filter(d => d.role === this.filterRole)
      }

      // Filter by enabled
      if (this.filterEnabled !== '') {
        const enabled = this.filterEnabled === 'true'
        result = result.filter(d => d.enabled === enabled)
      }

      // Sort
      result.sort((a, b) => {
        let aVal = a[this.sortField] ?? ''
        let bVal = b[this.sortField] ?? ''

        if (typeof aVal === 'boolean') {
          aVal = aVal ? 1 : 0
          bVal = bVal ? 1 : 0
        } else {
          aVal = String(aVal).toLowerCase()
          bVal = String(bVal).toLowerCase()
        }

        if (aVal < bVal) return this.sortDir === 'asc' ? -1 : 1
        if (aVal > bVal) return this.sortDir === 'asc' ? 1 : -1
        return 0
      })

      return result
    },
  },
  async mounted() {
    await Promise.all([
      this.loadDevices(),
      this.loadStats(),
      this.loadDeviceTypes(),
      this.loadDeviceRoles(),
    ])
  },
  methods: {
    async loadDevices() {
      this.loading = true
      try {
        const res = await axios.get('/api/device-management/')
        this.devices = res.data.devices || []
      } catch (e) {
        console.error('Failed to load devices:', e)
      } finally {
        this.loading = false
      }
    },
    async loadStats() {
      try {
        const res = await axios.get('/api/device-management/stats')
        this.stats = res.data
      } catch (e) {
        console.error('Failed to load stats:', e)
      }
    },
    async loadDeviceTypes() {
      try {
        const res = await axios.get('/api/device-management/types')
        this.deviceTypes = res.data.types || []
        console.log('Loaded device types:', this.deviceTypes.length)
      } catch (e) {
        console.error('Failed to load device types:', e)
        // Fallback значения
        this.deviceTypes = [
          { value: 'cisco_ios', label: 'Cisco IOS' },
          { value: 'cisco_iosxe', label: 'Cisco IOS-XE' },
          { value: 'cisco_nxos', label: 'Cisco Nexus NX-OS' },
          { value: 'arista_eos', label: 'Arista EOS' },
          { value: 'juniper_junos', label: 'Juniper Junos' },
        ]
      }
    },
    async loadDeviceRoles() {
      try {
        const res = await axios.get('/api/device-management/roles')
        this.deviceRoles = res.data.roles || []
        console.log('Loaded device roles:', this.deviceRoles.length)
      } catch (e) {
        console.error('Failed to load device roles:', e)
        // Fallback значения
        this.deviceRoles = [
          { value: 'switch', label: 'Switch' },
          { value: 'router', label: 'Router' },
          { value: 'firewall', label: 'Firewall' },
          { value: 'access-switch', label: 'Access Switch' },
          { value: 'core-switch', label: 'Core Switch' },
          { value: 'leaf', label: 'Leaf' },
          { value: 'spine', label: 'Spine' },
        ]
      }
    },
    getRoleLabel(value) {
      const role = this.deviceRoles.find(r => r.value === value)
      return role ? role.label : value
    },
    getTypeLabel(value) {
      const type = this.deviceTypes.find(t => t.value === value)
      return type ? type.label : value
    },
    sortBy(field) {
      if (this.sortField === field) {
        this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc'
      } else {
        this.sortField = field
        this.sortDir = 'asc'
      }
    },
    openAddModal() {
      this.editingDevice = null
      this.form = {
        host: '',
        device_type: 'cisco_ios',
        name: '',
        site: '',
        role: 'switch',
        tenant: '',
        description: '',
        enabled: true,
        tagsInput: '',
      }
      this.formError = ''
      this.showModal = true
    },
    openEditModal(device) {
      this.editingDevice = device
      this.form = {
        host: device.host,
        device_type: device.device_type,
        name: device.name || '',
        site: device.site || '',
        role: device.role || '',
        tenant: device.tenant || '',
        description: device.description || '',
        enabled: device.enabled,
        tagsInput: device.tags?.join(', ') || '',
      }
      this.formError = ''
      this.showModal = true
    },
    closeModal() {
      this.showModal = false
      this.editingDevice = null
      this.formError = ''
    },
    async saveDevice() {
      this.saving = true
      this.formError = ''

      const tags = this.form.tagsInput
        .split(',')
        .map(t => t.trim())
        .filter(t => t.length > 0)

      const data = {
        host: this.form.host,
        device_type: this.form.device_type,
        name: this.form.name || null,
        site: this.form.site || null,
        role: this.form.role || null,
        tenant: this.form.tenant || null,
        description: this.form.description || null,
        enabled: this.form.enabled,
        tags,
      }

      try {
        if (this.editingDevice) {
          await axios.put(`/api/device-management/${this.editingDevice.id}`, data)
        } else {
          await axios.post('/api/device-management/', data)
        }
        this.closeModal()
        await Promise.all([this.loadDevices(), this.loadStats()])
      } catch (e) {
        this.formError = e.response?.data?.detail || 'Ошибка сохранения'
      } finally {
        this.saving = false
      }
    },
    async toggleDevice(device) {
      try {
        await axios.post(`/api/device-management/${device.id}/toggle`, {
          enabled: !device.enabled,
        })
        device.enabled = !device.enabled
        await this.loadStats()
      } catch (e) {
        console.error('Failed to toggle device:', e)
      }
    },
    confirmDelete(device) {
      this.deviceToDelete = device
      this.showDeleteModal = true
    },
    async deleteDevice() {
      if (!this.deviceToDelete) return

      this.deleting = true
      try {
        await axios.delete(`/api/device-management/${this.deviceToDelete.id}`)
        this.showDeleteModal = false
        this.deviceToDelete = null
        await Promise.all([this.loadDevices(), this.loadStats()])
      } catch (e) {
        console.error('Failed to delete device:', e)
      } finally {
        this.deleting = false
      }
    },
    async migrateFromLegacy() {
      this.loading = true
      try {
        const res = await axios.post('/api/device-management/migrate')
        alert(res.data.message)
        await Promise.all([this.loadDevices(), this.loadStats()])
      } catch (e) {
        alert('Ошибка миграции: ' + (e.response?.data?.detail || e.message))
      } finally {
        this.loading = false
      }
    },

    // NetBox Import methods
    getStoredValue(key) {
      // Проверяем оба хранилища (как в Credentials.vue)
      return sessionStorage.getItem(key) || localStorage.getItem(key) || ''
    },
    openNetboxImportModal() {
      this.netboxResult = null
      this.netboxError = ''
      this.netboxProgress = 0
      this.netboxProgressText = ''
      // Подставляем сохранённые credentials из Credentials
      this.netboxForm.url = this.getStoredValue('netbox_url')
      this.netboxForm.token = this.getStoredValue('netbox_token')
      this.showNetboxModal = true
    },
    closeNetboxModal() {
      if (!this.netboxImporting) {
        this.showNetboxModal = false
      }
    },
    async importFromNetbox() {
      this.netboxImporting = true
      this.netboxError = ''
      this.netboxResult = null
      this.netboxProgress = 10
      this.netboxProgressText = 'Подключение к NetBox...'

      try {
        // Simulate progress while waiting for API
        const progressInterval = setInterval(() => {
          if (this.netboxProgress < 80) {
            this.netboxProgress += 5
            if (this.netboxProgress > 30 && this.netboxProgress < 60) {
              this.netboxProgressText = 'Получение устройств...'
            } else if (this.netboxProgress >= 60) {
              this.netboxProgressText = 'Импорт устройств...'
            }
          }
        }, 300)

        const res = await axios.post('/api/device-management/import-from-netbox', {
          netbox_url: this.netboxForm.url,
          netbox_token: this.netboxForm.token,
          site: this.netboxForm.site || null,
          role: this.netboxForm.role || null,
          status: this.netboxForm.status || null,
          replace: this.netboxForm.replace,
        })

        clearInterval(progressInterval)
        this.netboxProgress = 100
        this.netboxProgressText = 'Готово!'
        this.netboxResult = res.data

        // Reload devices
        await Promise.all([this.loadDevices(), this.loadStats()])

      } catch (e) {
        this.netboxError = e.response?.data?.detail || e.message || 'Ошибка импорта'
        this.netboxProgress = 0
        this.netboxProgressText = ''
      } finally {
        this.netboxImporting = false
      }
    },

    // File Import methods
    openFileImportModal() {
      this.selectedFile = null
      this.fileImportReplace = false
      this.fileImportResult = null
      this.fileImportError = ''
      this.fileImportProgress = 0
      this.fileImportProgressText = ''
      this.showFileImportModal = true
    },
    closeFileImportModal() {
      if (!this.fileImporting) {
        this.showFileImportModal = false
        this.selectedFile = null
        if (this.$refs.fileInput) {
          this.$refs.fileInput.value = ''
        }
      }
    },
    onFileSelected(event) {
      const file = event.target.files[0]
      if (file) {
        this.selectedFile = file
        this.fileImportResult = null
        this.fileImportError = ''
      }
    },
    formatFileSize(bytes) {
      if (bytes < 1024) return bytes + ' B'
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
      return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
    },
    async importFromFile() {
      if (!this.selectedFile) return

      this.fileImporting = true
      this.fileImportError = ''
      this.fileImportResult = null
      this.fileImportProgress = 10
      this.fileImportProgressText = 'Чтение файла...'

      try {
        // Progress simulation
        const progressInterval = setInterval(() => {
          if (this.fileImportProgress < 80) {
            this.fileImportProgress += 10
            if (this.fileImportProgress > 30) {
              this.fileImportProgressText = 'Импорт устройств...'
            }
          }
        }, 200)

        const formData = new FormData()
        formData.append('file', this.selectedFile)
        formData.append('replace', this.fileImportReplace)

        const res = await axios.post('/api/device-management/import-from-file', formData, {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        })

        clearInterval(progressInterval)
        this.fileImportProgress = 100
        this.fileImportProgressText = 'Готово!'
        this.fileImportResult = res.data

        // Reload devices
        await Promise.all([this.loadDevices(), this.loadStats()])

      } catch (e) {
        this.fileImportError = e.response?.data?.detail || e.message || 'Ошибка импорта'
        this.fileImportProgress = 0
        this.fileImportProgressText = ''
      } finally {
        this.fileImporting = false
      }
    },
  },
}
</script>

<style scoped>
.page h1 { margin-bottom: 5px; }
.subtitle { color: #666; margin-bottom: 20px; }

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.header-actions {
  display: flex;
  gap: 10px;
}

/* Stats */
.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 15px;
  margin-bottom: 20px;
}

.stat-card {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  text-align: center;
}

.stat-card.success { border-left: 4px solid #27ae60; }
.stat-card.warning { border-left: 4px solid #f39c12; }

.stat-value {
  font-size: 28px;
  font-weight: 600;
  color: #2c3e50;
}

.stat-label {
  font-size: 13px;
  color: #666;
  margin-top: 5px;
}

/* Filters */
.filters {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.search-input {
  flex: 1;
  min-width: 200px;
  padding: 10px 15px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}

.filters select {
  padding: 10px 15px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  background: white;
}

/* Buttons */
.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: #3498db;
  color: white;
}
.btn-primary:hover { background: #2980b9; }

.btn-secondary {
  background: #95a5a6;
  color: white;
}
.btn-secondary:hover { background: #7f8c8d; }

.btn-danger {
  background: #e74c3c;
  color: white;
}
.btn-danger:hover { background: #c0392b; }

.btn-light {
  background: #f8f9fa;
  color: #333;
  border: 1px solid #ddd;
}
.btn-light:hover { background: #e9ecef; }

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Table */
.table-container {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.devices-table {
  width: 100%;
  border-collapse: collapse;
}

.devices-table th,
.devices-table td {
  padding: 12px 15px;
  text-align: left;
  border-bottom: 1px solid #eee;
}

.devices-table th {
  background: #f8f9fa;
  font-weight: 600;
  font-size: 13px;
  color: #555;
}

.devices-table th.sortable {
  cursor: pointer;
}
.devices-table th.sortable:hover {
  background: #e9ecef;
}

.devices-table tr.disabled {
  opacity: 0.6;
  background: #f9f9f9;
}

.host-cell {
  font-family: monospace;
  font-weight: 500;
}

/* Toggle Switch */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  transition: 0.3s;
  border-radius: 24px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.3s;
  border-radius: 50%;
}

input:checked + .slider {
  background-color: #27ae60;
}

input:checked + .slider:before {
  transform: translateX(20px);
}

/* Type Badge */
.type-badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  background: #e9ecef;
}

.type-badge.cisco_ios,
.type-badge.cisco_iosxe { background: #e3f2fd; color: #1565c0; }
.type-badge.cisco_nxos { background: #f3e5f5; color: #7b1fa2; }
.type-badge.arista_eos { background: #e8f5e9; color: #2e7d32; }
.type-badge.juniper_junos { background: #fff3e0; color: #e65100; }

/* Role Badge */
.role-badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  background: #e9ecef;
  text-transform: capitalize;
}

.role-badge.switch { background: #e3f2fd; color: #1565c0; }
.role-badge.router { background: #e8f5e9; color: #2e7d32; }
.role-badge.firewall { background: #ffebee; color: #c62828; }
.role-badge.access-switch { background: #e3f2fd; color: #1976d2; }
.role-badge.distribution-switch { background: #e1f5fe; color: #0288d1; }
.role-badge.core-switch { background: #bbdefb; color: #1565c0; }
.role-badge.leaf { background: #c8e6c9; color: #388e3c; }
.role-badge.spine { background: #a5d6a7; color: #2e7d32; }

.description-cell {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #666;
  font-size: 13px;
}

/* Tags */
.tag {
  display: inline-block;
  padding: 2px 8px;
  margin-right: 4px;
  background: #e9ecef;
  border-radius: 4px;
  font-size: 11px;
}

.no-tags { color: #999; }

/* Actions */
.actions-cell {
  white-space: nowrap;
}

.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  padding: 5px 8px;
  font-size: 16px;
  opacity: 0.7;
  transition: opacity 0.2s;
}

.btn-icon:hover { opacity: 1; }
.btn-icon.danger:hover { color: #e74c3c; }

/* Empty State */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #666;
  background: white;
  border-radius: 8px;
}

.loading {
  text-align: center;
  padding: 40px;
  color: #666;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 12px;
  width: 100%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal.modal-small {
  max-width: 400px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #eee;
}

.modal-header h2 {
  margin: 0;
  font-size: 18px;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #999;
}

.modal-close:hover { color: #333; }

.modal-body {
  padding: 20px;
}

.modal-body .warning-text {
  color: #e74c3c;
  font-size: 13px;
  margin-top: 10px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 20px;
  border-top: 1px solid #eee;
}

/* Form */
.device-form {
  padding: 20px;
}

.form-group {
  margin-bottom: 15px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 5px;
  color: #333;
}

.form-group input,
.form-group select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: #3498db;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 15px;
}

.checkbox-group {
  margin-top: 10px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.checkbox-label input {
  width: auto;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #eee;
}

.form-error {
  margin-top: 15px;
  padding: 10px;
  background: #f8d7da;
  color: #721c24;
  border-radius: 6px;
  font-size: 13px;
}

/* NetBox Button */
.btn-netbox {
  background: linear-gradient(135deg, #2196F3, #1976D2);
  color: white;
  border: none;
}
.btn-netbox:hover:not(:disabled) {
  background: linear-gradient(135deg, #1976D2, #1565C0);
}
.btn-netbox:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

/* Progress Bar */
.progress-container {
  margin: 20px 0;
}

.progress-bar {
  height: 8px;
  background: #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #2196F3, #4CAF50);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-text {
  margin-top: 8px;
  font-size: 13px;
  color: #666;
  text-align: center;
}

/* Import Result */
.import-result {
  margin: 15px 0;
  padding: 15px;
  border-radius: 8px;
  font-size: 13px;
}

.import-result.success {
  background: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.import-result.error {
  background: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

.import-result p {
  margin: 5px 0;
}

/* File Input */
.file-input {
  width: 100%;
  padding: 10px;
  border: 2px dashed #ddd;
  border-radius: 8px;
  background: #f9f9f9;
  cursor: pointer;
  transition: border-color 0.2s;
}

.file-input:hover {
  border-color: #3498db;
}

.hint {
  margin-top: 5px;
  font-size: 12px;
  color: #888;
}

.selected-file {
  margin: 10px 0;
  padding: 10px 15px;
  background: #e8f4fd;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.file-name {
  font-weight: 500;
  color: #2c3e50;
}

.file-size {
  color: #666;
  font-size: 13px;
}
</style>
