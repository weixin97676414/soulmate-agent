import brandUrl from '@/assets/brand.png?inline'

/**
 * 品牌标识（用户提供的图：深色底 + 金色无限环）。
 *
 * ## 为什么用 `?inline`
 *
 * 打包后页面是通过 `file://` 加载的，而生产环境的 CSP 是
 * `img-src 'self' data: blob:`。`file://` 下的 `'self'` 能不能匹配本地图片属于
 * 实现细节，**不能赌** —— 一旦不匹配，界面上就是一个破图。
 * `?inline` 让 Vite 把图片转成 data URL，而 `data:` 是 CSP 明确允许的，
 * 从根上绕开这个问题。代价是图片进了 JS 包，所以只放了 128px 的版本
 * （界面里最大只用到 56px，128 足够覆盖 2x 屏）。
 *
 * ## 为什么统一走这个组件
 *
 * 原图**没有透明通道**（是实心深色底），所以每个使用点都必须自带圆角，
 * 否则在浅色主题下就是一个突兀的黑色方块。深色主题下它与背景同为深色，
 * 还需要一圈极细的描边把它和背景分开。
 *
 * 把"圆角 + 描边 + 尺寸"收在一处，避免四个调用点各写一遍然后慢慢长歪。
 */
export function BrandMark({
  size = 22,
  radius = 6,
  className = '',
  bordered = true,
}: {
  size?: number
  radius?: number
  className?: string
  /**
   * 是否要那圈描边。
   *
   * 默认 `true`（深色主题下原图与背景同为深色，不描边会糊成一片）。
   * 左上角标题栏传 `false`：那里的图标紧挨着当前搭子/群的头像，
   * 而头像是**没有边框**的（`AssistantAvatar` / `GroupAvatar` 都不带）——
   * 同一个位置上两种形态一个有边、一个没有，切来切去时会明显跳一下
   * （"剔除这个 logo 的边框"）。
   */
  bordered?: boolean
}) {
  return (
    <img
      src={brandUrl}
      alt="Soulmate Agent"
      width={size}
      height={size}
      draggable={false}
      // 用内联 style 而不是 Tailwind 的任意值语法：尺寸是运行时变量，
      // 拼出来的类名无法被 Tailwind 的静态扫描发现。
      style={{ width: size, height: size, borderRadius: radius }}
      className={`shrink-0 object-cover select-none ${bordered ? 'border border-line' : ''} ${className}`}
    />
  )
}
