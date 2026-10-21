
















import { useAppStore } from '@/stores/appStore'
import { useGroupStore } from '@/stores/groupStore'

















export function switchGroup(groupId: string): void {
  useAppStore.getState().setView('groups')
  void useGroupStore.getState().selectGroup(groupId)
}
