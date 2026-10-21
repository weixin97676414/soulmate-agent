import { useAppStore } from '@/stores/appStore'
import { useGroupStore } from '@/stores/groupStore'
import type { GroupProfile } from '@/types'



























export function inGroupContext(view: string): boolean {
  return view === 'groups' || window.agentBridge?.getWindowArgs?.()?.mode === 'group'
}







export function useCurrentGroup(): GroupProfile | undefined {
  const view = useAppStore((state) => state.view)
  const group = useGroupStore((state) =>
    state.groups.find((item) => item.id === state.selectedId),
  )
  return inGroupContext(view) ? group : undefined
}
