import { defineStore } from 'pinia'

const STORAGE_KEY = 'operator-name'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: localStorage.getItem(STORAGE_KEY) ?? '王安全',
    shiftLabel: '白班 08:00-20:00',
    scope: '矿山安全监测管理平台',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setOperator(name: string) {
      this.operator = name
      localStorage.setItem(STORAGE_KEY, name)
    },
  },
})
