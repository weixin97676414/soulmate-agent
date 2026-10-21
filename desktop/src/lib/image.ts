




















export const WALLPAPER_MAX_WIDTH = 1280














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
