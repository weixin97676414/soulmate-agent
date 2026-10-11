/**
 * 用户上传图片的统一处理：读成 data URL 并缩到合适尺寸。
 *
 * ## 为什么一定是 data URL

 * 打包后页面走 ``file://`` 加载，而生产 CSP 是 ``img-src 'self' data: blob:``。
 * ``file://`` 下的 ``'self'`` 能不能匹配本地图片属于**实现细节**（不同 Chromium
 * 版本行为并不一致），赌错了界面上就是一个破图 —— 而 ``data:`` 是明确允许的。
 * 所以用户上传的图一律转成 data URL 再存。
 *
 * ## 为什么必须压缩

 * 这些图最终存进 localStorage / 配置文件，而它们**通常只有 5 MB**。
 * 一张手机拍的 4000px 照片转成 base64 能轻松撑爆它 —— 到时不是"这张图没设上"，
 * 而是**连主题、折叠状态这些其它本地偏好一起写不进去**，症状和原因完全对不上。
 *
 * 抽成一个工具而不是在两处各写一遍，是因为壁纸和头像都要它，
 * 而"忘了压缩"这个坑只会以最难查的方式暴露。
 */

/** 壁纸最长边：够铺满窗口，又不会让 data URL 太大（约 200~400 KB） */
export const WALLPAPER_MAX_WIDTH = 1280

/** 助手头像：列表里只显示 20px，128 已经能覆盖高清屏 */
/**
 * 头像的最长边上限。
 *
 * ⚠️ 从 128 提到 **800**（产品要求"一律压缩为 800×800"）。
 * 128 是"列表里那一小块"够用的大小，但用户现在**能点头像看大图** ——
 * 128 放大会糊成一片马赛克。
 *
 * 为什么保持**等比缩放、不裁成正方形**：
 * - 显示端（`AssistantAvatar`）是方形容器 + `object-cover`，本来就会裁成方；
 * - 在这里裁成 800×800 会把偏构图的人脸切掉一角，而且**不可逆** ——
 *   用户看到的头像会突然少了一块，还得重新上传。存原比例只是多占一点体积。
 */
export const AVATAR_MAX_SIZE = 800

export async function readImageAsDataUrl(
  file: File,
  maxWidth: number,
  quality = 0.82,
): Promise<string> {
  const raw = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('读取图片失败'))
    reader.readAsDataURL(file)
  })

  return new Promise<string>((resolve) => {
    const image = new Image()
    image.onload = () => {
      const ratio = Math.min(1, maxWidth / image.width)
      const canvas = document.createElement('canvas')
      canvas.width = Math.round(image.width * ratio)
      canvas.height = Math.round(image.height * ratio)
      const ctx = canvas.getContext('2d')
      // 拿不到画布就退回原图：缩放只是优化，不该让"设图"这件事失败
      if (!ctx) {
        resolve(raw)
        return
      }
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
      resolve(canvas.toDataURL('image/jpeg', quality))
    }
    image.onerror = () => resolve(raw)
    image.src = raw
  })
}
