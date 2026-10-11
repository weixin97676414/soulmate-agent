/**
 * 极光动态背景。
 *
 * 纯 DOM + CSS，没有 canvas、没有 JS 动画 —— 全部交给 CSS：
 *   .aurora            定位 / 裁剪 / 皮肤透明度（在 index.css）
 *     .aurora-sway-x   横向摆动（11 秒一程，±28vw）
 *       .aurora-sway-y 纵向摆动（17 秒一程，±15vh）
 *         .aurora-field 那场光：三个 radial-gradient + 呼吸
 *
 * ⚠️ 两个 sway 的周期（11 / 17）互质，是为了看不出循环。
 * ⚠️ `aria-hidden`：它是纯装饰，读屏不该念到它。
 * ⚠️ 换皮肤 / 换壁纸都只改 `<html>` 上的属性，所以这里**不做任何判断**：
 *    有壁纸时由 CSS 把 `.aurora` 压成 `opacity: 0`（见 index.css），
 *    React 不需要因此重渲染一次。
 */
export function AuroraBackground() {
  return (
    <div className="aurora" aria-hidden>
      <div className="aurora-sway aurora-sway-x">
        <div className="aurora-sway aurora-sway-y">
          <div className="aurora-field" />
        </div>
      </div>
    </div>
  )
}
