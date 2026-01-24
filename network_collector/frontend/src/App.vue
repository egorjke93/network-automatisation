<template>
  <div class="app">
    <nav class="sidebar">
      <div class="logo">
        <h2>Network Collector</h2>
      </div>
      <ul class="nav-links">
        <li>
          <router-link to="/">Главная</router-link>
        </li>
        <li>
          <router-link to="/credentials">Credentials</router-link>
        </li>
        <li>
          <router-link to="/device-management">Device Management</router-link>
        </li>
        <li class="divider"></li>
        <li>
          <router-link to="/devices">Devices</router-link>
        </li>
        <li>
          <router-link to="/mac">MAC Table</router-link>
        </li>
        <li>
          <router-link to="/lldp">LLDP/CDP</router-link>
        </li>
        <li>
          <router-link to="/interfaces">Interfaces</router-link>
        </li>
        <li>
          <router-link to="/inventory">Inventory</router-link>
        </li>
        <li>
          <router-link to="/backup">Backup</router-link>
        </li>
        <li class="divider"></li>
        <li>
          <router-link to="/sync">Sync NetBox</router-link>
        </li>
        <li>
          <router-link to="/pipelines">Pipelines</router-link>
        </li>
        <li>
          <router-link to="/history">History</router-link>
        </li>
      </ul>
      <div class="status" :class="{ connected: credentialsSet }">
        {{ credentialsSet ? 'Credentials OK' : 'Not authenticated' }}
      </div>
    </nav>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'App',
  data() {
    return {
      credentialsSet: false,
    }
  },
  async mounted() {
    await this.checkCredentials()
    // Check every 10 seconds
    setInterval(this.checkCredentials, 10000)
  },
  methods: {
    async checkCredentials() {
      try {
        const res = await axios.get('/api/auth/credentials/status')
        this.credentialsSet = res.data.credentials_set
      } catch {
        this.credentialsSet = false
      }
    },
  },
}
</script>

<style>
.app {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 220px;
  background: #2c3e50;
  color: white;
  padding: 20px 0;
  display: flex;
  flex-direction: column;
}

.logo {
  padding: 0 20px 20px;
  border-bottom: 1px solid #34495e;
}

.logo h2 {
  font-size: 18px;
  font-weight: 600;
}

.nav-links {
  list-style: none;
  padding: 20px 0;
  flex: 1;
}

.nav-links li {
  margin: 0;
}

.nav-links li.divider {
  height: 1px;
  background: #34495e;
  margin: 10px 20px;
}

.nav-links a {
  display: block;
  padding: 10px 20px;
  color: #ecf0f1;
  text-decoration: none;
  font-size: 14px;
  transition: background 0.2s;
}

.nav-links a:hover {
  background: #34495e;
}

.nav-links a.router-link-exact-active {
  background: #3498db;
  font-weight: 500;
}

.status {
  padding: 15px 20px;
  font-size: 12px;
  background: #c0392b;
  text-align: center;
}

.status.connected {
  background: #27ae60;
}

.content {
  flex: 1;
  padding: 30px;
  overflow-y: auto;
}
</style>
