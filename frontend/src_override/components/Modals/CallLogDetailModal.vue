<template>
  <Dialog v-model="show">
    <template #body>
      <div class="bg-surface-modal px-4 pb-6 pt-5 sm:px-6">
        <div class="mb-5 flex items-center justify-between">
          <h3 class="text-2xl font-semibold leading-6 text-ink-gray-9">
            {{ __('Call Details') }}
          </h3>
          <Button variant="ghost" class="w-7" @click="show = false">
            <FeatherIcon name="x" class="h-4 w-4" />
          </Button>
        </div>

        <!-- Call Details in Table Format -->
        <div
          class="border rounded-md bg-white shadow-sm w-full overflow-y-auto max-h-[70vh]"
        >
          <table class="w-full text-left border-collapse">
            <tbody>
              <tr
                v-for="field in detailFields"
                :key="field.name"
                class="border-b last:border-0"
              >
                <td class="py-2 px-3 font-semibold text-gray-700">
                  {{ field.name }}
                </td>
                <td class="py-2 px-3">
                  <a
                    v-if="
                      field.name === 'Custom External Recording Url' ||
                      (field.name === 'Custom Audio File' &&
                        field.value !== 'N/A')
                    "
                    :href="field.value"
                    target="_blank"
                    class="text-blue-500 hover:underline"
                  >
                    {{
                      field.name === 'Custom Audio File'
                        ? 'Open Audio File'
                        : 'Open Recording'
                    }}
                  </a>
                  <pre v-else class="whitespace-pre-wrap">{{
                    field.value
                  }}</pre>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { FeatherIcon } from 'frappe-ui'
import { computed, nextTick } from 'vue'

const show = defineModel()

const callLog = defineModel('callLog')

const detailFields = computed(() => {
  if (!callLog.value?.data) return []

  let data = JSON.parse(JSON.stringify(callLog.value?.data))

  return Object.entries(data).map(([key, value]) => ({
    name: formatFieldName(key),
    value: formatValue(value),
    isLink: key === 'custom_external_recording_url' && value, // If field is 'custom_external_recording_url', make it a link
  }))
})

// Convert field names from snake_case to human-readable format
function formatFieldName(key) {
  return key
    .replace(/_/g, ' ') // Replace underscores with spaces
    .replace(/\b\w/g, (c) => c.toUpperCase()) // Capitalize first letter of each word
}

// Format values (handle nested objects & arrays)
function formatValue(value) {
  if (value === null || value === undefined || value === '') return 'N/A'
  if (typeof value === 'object') {
    if (Array.isArray(value)) {
      return value.length ? JSON.stringify(value, null, 2) : 'N/A'
    }
    return JSON.stringify(value, null, 2) // Pretty print objects
  }
  return value
}
</script>

<style scoped>
.audio-control {
  height: 36px;
  outline: none;
  border-radius: 10px;
  cursor: pointer;
  background-color: rgb(237, 237, 237);
}

audio::-webkit-media-controls-panel {
  background-color: rgb(237, 237, 237) !important;
}

.audio-control::-webkit-media-controls-panel {
  background-color: white;
}
</style>
