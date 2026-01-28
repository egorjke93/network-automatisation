<template>
  <div class="data-table-wrapper">
    <!-- Toolbar -->
    <div class="table-toolbar">
      <div class="search-box">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Поиск..."
          class="search-input"
        />
        <span class="search-icon">🔍</span>
      </div>

      <div class="toolbar-right">
        <span class="row-count">{{ filteredData.length }} записей</span>

        <div class="export-buttons" v-if="exportable">
          <button class="btn-export" @click="exportJSON" title="Экспорт в JSON">
            JSON
          </button>
          <button class="btn-export" @click="exportCSV" title="Экспорт в CSV">
            CSV
          </button>
          <button class="btn-export" @click="exportExcel" title="Экспорт в Excel">
            Excel
          </button>
        </div>
      </div>
    </div>

    <!-- Table -->
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th
              v-for="col in columns"
              :key="col.key"
              @click="sortBy(col.key)"
              :class="{ sortable: col.sortable !== false, sorted: sortKey === col.key }"
            >
              {{ col.label }}
              <span v-if="sortKey === col.key" class="sort-icon">
                {{ sortOrder === 'asc' ? '▲' : '▼' }}
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in paginatedData" :key="index">
            <td v-for="col in columns" :key="col.key">
              <slot :name="`cell-${col.key}`" :value="row[col.key]" :row="row">
                {{ formatCell(row[col.key], col) }}
              </slot>
            </td>
          </tr>
          <tr v-if="filteredData.length === 0">
            <td :colspan="columns.length" class="empty-row">
              {{ searchQuery ? 'Ничего не найдено' : 'Нет данных' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div class="pagination" v-if="totalPages > 1">
      <button
        class="page-btn"
        @click="currentPage = 1"
        :disabled="currentPage === 1"
      >
        «
      </button>
      <button
        class="page-btn"
        @click="currentPage--"
        :disabled="currentPage === 1"
      >
        ‹
      </button>

      <span class="page-info">
        Страница {{ currentPage }} из {{ totalPages }}
      </span>

      <button
        class="page-btn"
        @click="currentPage++"
        :disabled="currentPage === totalPages"
      >
        ›
      </button>
      <button
        class="page-btn"
        @click="currentPage = totalPages"
        :disabled="currentPage === totalPages"
      >
        »
      </button>

      <select v-model="pageSize" class="page-size-select">
        <option :value="25">25</option>
        <option :value="50">50</option>
        <option :value="100">100</option>
        <option :value="500">500</option>
      </select>
    </div>
  </div>
</template>

<script>
export default {
  name: 'DataTable',
  props: {
    data: {
      type: Array,
      required: true,
    },
    columns: {
      type: Array,
      required: true,
      // [{ key: 'hostname', label: 'Hostname', sortable: true, type: 'string' }]
    },
    exportable: {
      type: Boolean,
      default: true,
    },
    exportFilename: {
      type: String,
      default: 'export',
    },
  },
  data() {
    return {
      searchQuery: '',
      sortKey: '',
      sortOrder: 'asc',
      currentPage: 1,
      pageSize: 50,
    }
  },
  computed: {
    filteredData() {
      let result = [...this.data]

      // Search filter
      if (this.searchQuery) {
        const query = this.searchQuery.toLowerCase()
        result = result.filter(row => {
          return this.columns.some(col => {
            const value = row[col.key]
            if (value === null || value === undefined) return false
            return String(value).toLowerCase().includes(query)
          })
        })
      }

      // Sort
      if (this.sortKey) {
        result.sort((a, b) => {
          let aVal = a[this.sortKey]
          let bVal = b[this.sortKey]

          // Handle null/undefined
          if (aVal === null || aVal === undefined) aVal = ''
          if (bVal === null || bVal === undefined) bVal = ''

          // Numeric comparison
          const aNum = parseFloat(aVal)
          const bNum = parseFloat(bVal)
          if (!isNaN(aNum) && !isNaN(bNum)) {
            return this.sortOrder === 'asc' ? aNum - bNum : bNum - aNum
          }

          // String comparison
          const aStr = String(aVal).toLowerCase()
          const bStr = String(bVal).toLowerCase()
          if (this.sortOrder === 'asc') {
            return aStr.localeCompare(bStr)
          }
          return bStr.localeCompare(aStr)
        })
      }

      return result
    },
    totalPages() {
      return Math.ceil(this.filteredData.length / this.pageSize)
    },
    paginatedData() {
      const start = (this.currentPage - 1) * this.pageSize
      return this.filteredData.slice(start, start + this.pageSize)
    },
  },
  watch: {
    searchQuery() {
      this.currentPage = 1
    },
    data() {
      this.currentPage = 1
    },
  },
  methods: {
    sortBy(key) {
      const col = this.columns.find(c => c.key === key)
      if (col && col.sortable === false) return

      if (this.sortKey === key) {
        this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc'
      } else {
        this.sortKey = key
        this.sortOrder = 'asc'
      }
    },
    formatCell(value, col) {
      if (value === null || value === undefined) return '-'
      if (col.type === 'boolean') return value ? 'Yes' : 'No'
      return value
    },
    exportJSON() {
      const json = JSON.stringify(this.filteredData, null, 2)
      this.downloadFile(json, `${this.exportFilename}.json`, 'application/json')
    },
    exportCSV() {
      const headers = this.columns.map(c => c.label).join(',')
      const rows = this.filteredData.map(row => {
        return this.columns.map(col => {
          let val = row[col.key]
          if (val === null || val === undefined) val = ''
          // Escape quotes and wrap in quotes if contains comma
          val = String(val).replace(/"/g, '""')
          if (val.includes(',') || val.includes('"') || val.includes('\n')) {
            val = `"${val}"`
          }
          return val
        }).join(',')
      })

      const csv = [headers, ...rows].join('\n')
      this.downloadFile(csv, `${this.exportFilename}.csv`, 'text/csv')
    },
    exportExcel() {
      // Simple HTML table export that Excel can open
      let html = '<html><head><meta charset="UTF-8"></head><body>'
      html += '<table border="1">'

      // Headers
      html += '<tr>'
      this.columns.forEach(col => {
        html += `<th style="background:#f0f0f0;font-weight:bold">${col.label}</th>`
      })
      html += '</tr>'

      // Data
      this.filteredData.forEach(row => {
        html += '<tr>'
        this.columns.forEach(col => {
          let val = row[col.key]
          if (val === null || val === undefined) val = ''
          html += `<td>${this.escapeHtml(String(val))}</td>`
        })
        html += '</tr>'
      })

      html += '</table></body></html>'
      this.downloadFile(html, `${this.exportFilename}.xls`, 'application/vnd.ms-excel')
    },
    escapeHtml(str) {
      return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
    },
    downloadFile(content, filename, mimeType) {
      const blob = new Blob([content], { type: mimeType + ';charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    },
  },
}
</script>

<style scoped>
.data-table-wrapper {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 20px;
  border-bottom: 1px solid #eee;
  gap: 15px;
  flex-wrap: wrap;
}

.search-box {
  position: relative;
  flex: 1;
  max-width: 300px;
}

.search-input {
  width: 100%;
  padding: 8px 12px 8px 35px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.search-input:focus {
  outline: none;
  border-color: #3498db;
}

.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 14px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 15px;
}

.row-count {
  color: #666;
  font-size: 13px;
}

.export-buttons {
  display: flex;
  gap: 5px;
}

.btn-export {
  padding: 6px 12px;
  border: 1px solid #ddd;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-export:hover {
  background: #f8f9fa;
  border-color: #3498db;
  color: #3498db;
}

.table-container {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th, td {
  padding: 12px 15px;
  text-align: left;
  border-bottom: 1px solid #eee;
  white-space: nowrap;
}

th {
  background: #f8f9fa;
  font-weight: 600;
  font-size: 13px;
  color: #555;
  user-select: none;
}

th.sortable {
  cursor: pointer;
}

th.sortable:hover {
  background: #e9ecef;
}

th.sorted {
  background: #e3f2fd;
  color: #1976d2;
}

.sort-icon {
  margin-left: 5px;
  font-size: 10px;
}

td {
  font-size: 14px;
}

tr:hover td {
  background: #f8f9fa;
}

.empty-row {
  text-align: center;
  color: #999;
  padding: 30px;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 15px;
  border-top: 1px solid #eee;
}

.page-btn {
  padding: 6px 12px;
  border: 1px solid #ddd;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.page-btn:hover:not(:disabled) {
  background: #f8f9fa;
  border-color: #3498db;
}

.page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: 13px;
  color: #666;
}

.page-size-select {
  padding: 5px 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
  margin-left: 10px;
}
</style>
