/**
 * ⚠️ **兼容转发文件**（恢复 版本时补的）。
 *
 * 恢复出来的代码里，`ContextMenu` 组件本体在 `@/components/ui/ContextMenu`，
 * 但有四个文件（`SessionList` / `AssistantRail` / `GroupChatPage` / `GroupContextMenu`）
 * import 的是旧路径 `@/components/ContextMenu` —— 那是这次恢复时"不同文件取自不同日期"
 * 造成的版本错位，不是代码本身的缺陷。
 *
 * 与其改那四个文件的 import（会掩盖错位来源），这里放一个转发：
 * 两条路径都能用，等把版本对齐后可以删掉本文件。
 */
export * from './ui/ContextMenu'
