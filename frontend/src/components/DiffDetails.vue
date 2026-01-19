<template>
  <div class="diff-details-component" v-if="hasAnyChanges">
    <!-- Summary counts -->
    <div class="summary-row">
      <span class="count created" v-if="counts.created">+{{ counts.created }} создано</span>
      <span class="count updated" v-if="counts.updated">~{{ counts.updated }} обновлено</span>
      <span class="count deleted" v-if="counts.deleted">-{{ counts.deleted }} удалено</span>
      <span class="count skipped" v-if="counts.skipped">={{ counts.skipped }} пропущено</span>
    </div>

    <!-- Details preview (first N items) -->
    <div class="details-preview" v-if="showPreview && hasDetails">
      <div class="preview-section" v-if="details.create && details.create.length">
        <span class="section-label created">Создано:</span>
        <span v-for="(item, i) in details.create.slice(0, limit)" :key="'c'+i" class="item">
          {{ formatItem(item) }}
        </span>
        <span v-if="details.create.length > limit" class="more">+{{ details.create.length - limit }}</span>
      </div>
      <div class="preview-section" v-if="details.update && details.update.length">
        <span class="section-label updated">Обновлено:</span>
        <span v-for="(item, i) in details.update.slice(0, limit)" :key="'u'+i" class="item">
          {{ formatItem(item) }}
        </span>
        <span v-if="details.update.length > limit" class="more">+{{ details.update.length - limit }}</span>
      </div>
      <div class="preview-section" v-if="details.delete && details.delete.length">
        <span class="section-label deleted">Удалено:</span>
        <span v-for="(item, i) in details.delete.slice(0, limit)" :key="'d'+i" class="item">
          {{ formatItem(item) }}
        </span>
        <span v-if="details.delete.length > limit" class="more">+{{ details.delete.length - limit }}</span>
      </div>
    </div>

    <!-- Link to history for full details -->
    <router-link v-if="showHistoryLink" to="/history" class="history-link">
      Полные детали в Истории →
    </router-link>
  </div>
</template>

<script>
export default {
  name: 'DiffDetails',
  props: {
    counts: {
      type: Object,
      default: () => ({ created: 0, updated: 0, deleted: 0, skipped: 0 })
    },
    details: {
      type: Object,
      default: () => ({})
    },
    showPreview: {
      type: Boolean,
      default: true
    },
    showHistoryLink: {
      type: Boolean,
      default: false
    },
    limit: {
      type: Number,
      default: 5
    }
  },
  computed: {
    hasAnyChanges() {
      return this.counts.created > 0 || this.counts.updated > 0 ||
             this.counts.deleted > 0 || this.counts.skipped > 0
    },
    hasDetails() {
      if (!this.details) return false
      return (this.details.create && this.details.create.length > 0) ||
             (this.details.update && this.details.update.length > 0) ||
             (this.details.delete && this.details.delete.length > 0)
    }
  },
  methods: {
    formatItem(item) {
      if (typeof item === 'string') return item
      return item.name || item.address || item.entity_name || JSON.stringify(item)
    }
  }
}
</script>

<style scoped>
.diff-details-component {
  margin-top: 8px;
}

.summary-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
}

.count {
  font-size: 13px;
  padding: 3px 8px;
  border-radius: 4px;
  background: #f8f9fa;
}
.count.created { color: #28a745; }
.count.updated { color: #007bff; }
.count.deleted { color: #dc3545; }
.count.skipped { color: #6c757d; }

.details-preview {
  padding: 10px;
  background: #fff;
  border: 1px solid #e9ecef;
  border-radius: 4px;
  margin-bottom: 8px;
}

.preview-section {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.preview-section:last-child { margin-bottom: 0; }

.section-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  min-width: 80px;
}
.section-label.created { color: #28a745; }
.section-label.updated { color: #007bff; }
.section-label.deleted { color: #dc3545; }

.item {
  font-size: 12px;
  padding: 2px 6px;
  background: #f8f9fa;
  border-radius: 3px;
  color: #495057;
}

.more {
  font-size: 11px;
  color: #6c757d;
  font-style: italic;
}

.history-link {
  font-size: 12px;
  color: #007bff;
  text-decoration: none;
}
.history-link:hover {
  text-decoration: underline;
}
</style>
