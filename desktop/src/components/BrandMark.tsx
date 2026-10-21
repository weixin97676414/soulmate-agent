import brandUrl from '@/assets/brand.png?inline'



























export function BrandMark({
  size = 22,
  radius = 6,
  className = '',
  bordered = true,
}: {
  size?: number
  radius?: number
  className?: string
  








  bordered?: boolean
}) {
  return (
    <img
      src={brandUrl}
      alt="Soulmate Agent"
      width={size}
      height={size}
      draggable={false}
      
      
      style={{ width: size, height: size, borderRadius: radius }}
      className={`shrink-0 object-cover select-none ${bordered ? 'border border-line' : ''} ${className}`}
    />
  )
}
