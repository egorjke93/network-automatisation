<template>
  <div class="credentials">
    <h1>Credentials</h1>
    <p class="subtitle">Настройка SSH и NetBox credentials</p>

    <div class="security-notice">
      <strong>🔒 Безопасность:</strong> Credentials хранятся только в браузере и передаются в каждом запросе.
      Сервер НЕ сохраняет пароли.
    </div>

    <div class="storage-toggle">
      <label>
        <input type="radio" v-model="storageType" value="session" />
        Только для этой сессии <span class="hint">(удалится при закрытии вкладки)</span>
      </label>
      <label>
        <input type="radio" v-model="storageType" value="local" />
        Сохранить постоянно <span class="hint">(останется в браузере)</span>
      </label>
    </div>

    <div class="forms">
      <!-- SSH Credentials -->
      <div class="form-card">
        <h3>SSH Credentials</h3>
        <div class="status-badge" :class="{ active: sshStatus }">
          {{ sshStatus ? 'Установлено' : 'Не установлено' }}
        </div>

        <form @submit.prevent="setSshCredentials">
          <div class="form-group">
            <label>Username</label>
            <input v-model="ssh.username" type="text" required placeholder="admin" />
          </div>
          <div class="form-group">
            <label>Password</label>
            <input v-model="ssh.password" type="password" required placeholder="********" />
          </div>
          <div class="buttons">
            <button type="submit" class="btn primary">Сохранить</button>
            <button type="button" class="btn danger" @click="deleteSshCredentials" v-if="sshStatus">
              Удалить
            </button>
          </div>
        </form>
      </div>

      <!-- NetBox Config -->
      <div class="form-card">
        <h3>NetBox Config</h3>
        <div class="status-badge" :class="{ active: netboxStatus }">
          {{ netboxStatus ? 'Настроено' : 'Не настроено' }}
        </div>

        <form @submit.prevent="setNetboxConfig">
          <div class="form-group">
            <label>URL</label>
            <input v-model="netbox.url" type="url" required placeholder="http://netbox.local:8000" />
          </div>
          <div class="form-group">
            <label>API Token</label>
            <input v-model="netbox.token" type="password" required placeholder="0123456789abcdef..." />
          </div>
          <div class="buttons">
            <button type="submit" class="btn primary">Сохранить</button>
            <button type="button" class="btn danger" @click="deleteNetboxConfig" v-if="netboxStatus">
              Удалить
            </button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="message" class="message" :class="messageType">
      {{ message }}
    </div>
  </div>
</template>

<script>
export default {
  name: 'Credentials',
  data() {
    return {
      ssh: { username: '', password: '' },
      netbox: { url: '', token: '' },
      sshStatus: false,
      netboxStatus: false,
      storageType: 'session', // 'session' или 'local'
      message: '',
      messageType: 'success',
    }
  },
  computed: {
    storage() {
      return this.storageType === 'local' ? localStorage : sessionStorage
    }
  },
  mounted() {
    this.loadCredentials()
  },
  methods: {
    getStorage(key) {
      // Проверяем оба хранилища
      return sessionStorage.getItem(key) || localStorage.getItem(key)
    },
    loadCredentials() {
      // SSH
      const username = this.getStorage('ssh_username')
      const password = this.getStorage('ssh_password')
      if (username) {
        this.ssh.username = username
        this.sshStatus = true
        // Определяем тип хранилища
        this.storageType = localStorage.getItem('ssh_username') ? 'local' : 'session'
      }
      if (password) {
        this.ssh.password = password
      }

      // NetBox
      const url = this.getStorage('netbox_url')
      const token = this.getStorage('netbox_token')
      if (url) {
        this.netbox.url = url
        this.netboxStatus = true
      }
      if (token) {
        this.netbox.token = token
      }
    },
    setSshCredentials() {
      // Очищаем оба хранилища сначала
      sessionStorage.removeItem('ssh_username')
      sessionStorage.removeItem('ssh_password')
      localStorage.removeItem('ssh_username')
      localStorage.removeItem('ssh_password')

      // Сохраняем в выбранное
      this.storage.setItem('ssh_username', this.ssh.username)
      this.storage.setItem('ssh_password', this.ssh.password)

      this.sshStatus = true
      const where = this.storageType === 'local' ? 'постоянно' : 'в сессии'
      this.showMessage(`SSH credentials сохранены ${where}`, 'success')
    },
    deleteSshCredentials() {
      sessionStorage.removeItem('ssh_username')
      sessionStorage.removeItem('ssh_password')
      localStorage.removeItem('ssh_username')
      localStorage.removeItem('ssh_password')

      this.ssh = { username: '', password: '' }
      this.sshStatus = false
      this.showMessage('SSH credentials удалены', 'success')
    },
    setNetboxConfig() {
      // Очищаем оба хранилища сначала
      sessionStorage.removeItem('netbox_url')
      sessionStorage.removeItem('netbox_token')
      localStorage.removeItem('netbox_url')
      localStorage.removeItem('netbox_token')

      // Сохраняем в выбранное
      this.storage.setItem('netbox_url', this.netbox.url)
      this.storage.setItem('netbox_token', this.netbox.token)

      this.netboxStatus = true
      const where = this.storageType === 'local' ? 'постоянно' : 'в сессии'
      this.showMessage(`NetBox config сохранён ${where}`, 'success')
    },
    deleteNetboxConfig() {
      sessionStorage.removeItem('netbox_url')
      sessionStorage.removeItem('netbox_token')
      localStorage.removeItem('netbox_url')
      localStorage.removeItem('netbox_token')

      this.netbox = { url: '', token: '' }
      this.netboxStatus = false
      this.showMessage('NetBox config удалён', 'success')
    },
    showMessage(text, type) {
      this.message = text
      this.messageType = type
      setTimeout(() => { this.message = '' }, 3000)
    },
  },
}
</script>

<style scoped>
.credentials h1 {
  margin-bottom: 10px;
}

.subtitle {
  color: #666;
  margin-bottom: 30px;
}

.forms {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: 20px;
}

.form-card {
  background: white;
  padding: 25px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.form-card h3 {
  margin-bottom: 15px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  background: #e74c3c;
  color: white;
  margin-bottom: 15px;
}

.status-badge.active {
  background: #27ae60;
}

.form-group {
  margin-bottom: 15px;
}

.form-group label {
  display: block;
  margin-bottom: 5px;
  font-weight: 500;
  font-size: 14px;
}

.form-group input {
  width: 100%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.form-group input:focus {
  border-color: #3498db;
  outline: none;
}

.buttons {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.btn.primary {
  background: #3498db;
  color: white;
}

.btn.primary:hover {
  background: #2980b9;
}

.btn.danger {
  background: #e74c3c;
  color: white;
}

.btn.danger:hover {
  background: #c0392b;
}

.message {
  margin-top: 20px;
  padding: 15px;
  border-radius: 4px;
}

.message.success {
  background: #d4edda;
  color: #155724;
}

.message.error {
  background: #f8d7da;
  color: #721c24;
}

.security-notice {
  background: #e8f4fd;
  border: 1px solid #b8daff;
  border-radius: 4px;
  padding: 12px 15px;
  margin-bottom: 20px;
  color: #004085;
  font-size: 14px;
}

.storage-toggle {
  display: flex;
  gap: 20px;
  margin-bottom: 25px;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 6px;
}

.storage-toggle label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
}

.storage-toggle input[type="radio"] {
  width: 16px;
  height: 16px;
}

.storage-toggle .hint {
  color: #666;
  font-size: 12px;
}
</style>
