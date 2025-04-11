<template>
  <ListView
    :columns="columns"
    :rows="rows"
    :options="{
      onRowClick: (row) => {
        emit('showCallLog', row.custom_tata_smart_flow_call_log_id)
      },
      selectable: options.selectable,
      showTooltip: options.showTooltip,
      resizeColumn: options.resizeColumn,
    }"
    row-key="name"
    v-bind="$attrs"
  >
    <ListHeader
      class="sm:mx-5 mx-3"
      @columnWidthUpdated="emit('columnWidthUpdated')"
    >
      <ListHeaderItem
        v-for="column in columns"
        :key="column.key"
        :item="column"
        @columnWidthUpdated="emit('columnWidthUpdated', column)"
      >
        <Button
          v-if="column.key == '_liked_by'"
          variant="ghosted"
          class="!h-4"
          :class="isLikeFilterApplied ? 'fill-red-500' : 'fill-white'"
          @click="() => emit('applyLikeFilter')"
        >
          <HeartIcon class="h-4 w-4" />
        </Button>
      </ListHeaderItem>
    </ListHeader>
    <ListRows
      class="mx-3 sm:mx-5"
      :rows="rows"
      v-slot="{ idx, column, item }"
      doctype="CRM Call Log"
    >
      <ListRowItem :item="item" :align="column.align">
        <template #prefix>
          <div v-if="['caller', 'receiver'].includes(column.key)">
            <Avatar
              v-if="item.label"
              class="flex items-center"
              :image="item.image"
              :label="item.label"
              size="sm"
            />
          </div>
          <div v-else-if="['type', 'duration'].includes(column.key)">
            <FeatherIcon :name="item.icon" class="h-3 w-3" />
          </div>
        </template>
        <template #default="{ label }">
          <div
            v-if="['modified', 'creation'].includes(column.key)"
            class="truncate text-base"
            @click="
              (event) =>
                emit('applyFilter', {
                  event,
                  idx,
                  column,
                  item,
                  firstColumn: columns[0],
                })
            "
          >
            <Tooltip :text="item.label">
              <div>{{ item.timeAgo }}</div>
            </Tooltip>
          </div>
          <div
            v-else-if="column.key === 'custom_call_log_status'"
            class="truncate text-base"
          >
            <Badge
              :variant="'subtle'"
              :theme="item.color"
              size="md"
              :label="__(item.label)"
              @click="
                (event) =>
                  emit('applyFilter', {
                    event,
                    idx,
                    column,
                    item,
                    firstColumn: columns[0],
                  })
              "
            />
          </div>
          <div v-else-if="column.type === 'Check'">
            <FormControl
              type="checkbox"
              :modelValue="item"
              :disabled="true"
              class="text-ink-gray-9"
            />
          </div>
          <div v-else-if="column.key === '_liked_by'">
            <Button
              v-if="column.key == '_liked_by'"
              variant="ghosted"
              :class="isLiked(item) ? 'fill-red-500' : 'fill-white'"
              @click.stop.prevent="
                () => emit('likeDoc', { name: row.name, liked: isLiked(item) })
              "
            >
              <HeartIcon class="h-4 w-4" />
            </Button>
          </div>
          <div
            v-else
            class="truncate text-base"
            @click="
              (event) =>
                emit('applyFilter', {
                  event,
                  idx,
                  column,
                  item,
                  firstColumn: columns[0],
                })
            "
          >
            {{ label }}
          </div>
        </template>
      </ListRowItem>
    </ListRows>
    <div class="flex justify-between mt-4 border-t p-3 items-center">
      <!-- Previous Page Button -->
      <button
        @click="props.viewControls?.prevPage()"
        :disabled="
          props.viewControls?.isLoading || props.viewControls?.currentPage === 1
        "
        class="bg-gray-500 text-white px-4 py-2 rounded disabled:opacity-50"
      >
        Previous
      </button>

      <!-- Page Info -->
      <span class="text-gray-700">
        Page {{ props.viewControls?.currentPage }} of
        {{ props.viewControls?.totalPages }}
      </span>

      <!-- Total Records -->
      <span class="text-gray-700"
        >Total Records: {{ props.viewControls?.totalRecords }}</span
      >

      <!-- Limit Dropdown -->
      <div class="flex items-center gap-2">
        <span class="text-gray-700">Show</span>

        <select
          v-model="props.viewControls.pageSize"
          @change="props.viewControls?.updatePageSize()"
          :disabled="props.viewControls?.isLoading"
          class="border rounded px-6 py-1 cursor-pointer appearance-none bg-white"
        >
          <option v-for="size in [20, 50, 100]" :key="size" :value="size">
            {{ size }}
          </option>
        </select>

        <span class="text-gray-700">per page</span>
      </div>

      <!-- Next Page Button -->
      <button
        @click="props.viewControls?.nextPage()"
        :disabled="
          props.viewControls?.isLoading ||
          props.viewControls?.currentPage * props.viewControls?.pageSize >=
            props.viewControls?.totalRecords
        "
        class="bg-blue-500 text-white px-4 py-2 rounded disabled:opacity-50"
      >
        Next
      </button>
    </div>

    <ListSelectBanner>
      <template #actions="{ selections, unselectAll }">
        <Dropdown
          :options="listBulkActionsRef.bulkActions(selections, unselectAll)"
        >
          <Button icon="more-horizontal" variant="ghost" />
        </Dropdown>
      </template>
    </ListSelectBanner>
  </ListView>
  <ListBulkActions
    ref="listBulkActionsRef"
    v-model="list"
    doctype="CRM Call Log"
    :options="{
      hideEdit: true,
      hideAssign: true,
    }"
  />
</template>
<script setup>
import HeartIcon from '@/components/Icons/HeartIcon.vue'
import ListBulkActions from '@/components/ListBulkActions.vue'
import ListRows from '@/components/ListViews/ListRows.vue'
import {
  Avatar,
  ListView,
  ListHeader,
  ListHeaderItem,
  ListSelectBanner,
  ListRowItem,
  ListFooter,
  Tooltip,
  Dropdown,
} from 'frappe-ui'
import { sessionStore } from '@/stores/session'
import { ref, computed, watch } from 'vue'
const props = defineProps({
  viewControls: Object,
  rows: {
    type: Array,
    required: true,
  },
  columns: {
    type: Array,
    required: true,
  },
  options: {
    type: Object,
    default: () => ({
      selectable: true,
      showTooltip: true,
      resizeColumn: false,
      totalCount: 0,
      rowCount: 0,
    }),
  },
})

const emit = defineEmits([
  'showCallLog',
  'loadMore',
  'updatePageCount',
  'columnWidthUpdated',
  'applyFilter',
  'applyLikeFilter',
  'likeDoc',
])

const pageLengthCount = defineModel()
const list = defineModel('list')

const isLikeFilterApplied = computed(() => {
  return list.value.params?.filters?._liked_by ? true : false
})

const { user } = sessionStore()

function isLiked(item) {
  if (item) {
    let likedByMe = JSON.parse(item)
    return likedByMe.includes(user)
  }
}

watch(pageLengthCount, (val, old_value) => {
  if (val === old_value) return
  emit('updatePageCount', val)
})

const listBulkActionsRef = ref(null)

defineExpose({
  customListActions: computed(
    () => listBulkActionsRef.value?.customListActions,
  ),
})
</script>
