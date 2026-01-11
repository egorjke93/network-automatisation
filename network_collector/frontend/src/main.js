import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import axios from 'axios'
import App from './App.vue'

// Views
import Home from './views/Home.vue'
import Credentials from './views/Credentials.vue'
import Devices from './views/Devices.vue'
import Mac from './views/Mac.vue'
import Lldp from './views/Lldp.vue'
import Interfaces from './views/Interfaces.vue'
import Inventory from './views/Inventory.vue'
import Backup from './views/Backup.vue'
import Sync from './views/Sync.vue'
import Pipelines from './views/Pipelines.vue'
import History from './views/History.vue'
import DeviceManagement from './views/DeviceManagement.vue'

// =============================================================================
// Axios configuration - credentials из sessionStorage в каждый запрос
// =============================================================================

// Helper: проверяем sessionStorage, потом localStorage
const getCredential = (key) => sessionStorage.getItem(key) || localStorage.getItem(key)

axios.interceptors.request.use((config) => {
  // SSH credentials (проверяем оба хранилища)
  const sshUsername = getCredential('ssh_username')
  const sshPassword = getCredential('ssh_password')
  if (sshUsername) config.headers['X-SSH-Username'] = sshUsername
  if (sshPassword) config.headers['X-SSH-Password'] = sshPassword

  // NetBox config (проверяем оба хранилища)
  const netboxUrl = getCredential('netbox_url')
  const netboxToken = getCredential('netbox_token')
  if (netboxUrl) config.headers['X-NetBox-URL'] = netboxUrl
  if (netboxToken) config.headers['X-NetBox-Token'] = netboxToken

  return config
})

// =============================================================================
// Routes
// =============================================================================

const routes = [
  { path: '/', component: Home },
  { path: '/credentials', component: Credentials },
  { path: '/devices', component: Devices },
  { path: '/mac', component: Mac },
  { path: '/lldp', component: Lldp },
  { path: '/interfaces', component: Interfaces },
  { path: '/inventory', component: Inventory },
  { path: '/backup', component: Backup },
  { path: '/sync', component: Sync },
  { path: '/pipelines', component: Pipelines },
  { path: '/history', component: History },
  { path: '/device-management', component: DeviceManagement },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

const app = createApp(App)
app.use(router)
app.mount('#app')
