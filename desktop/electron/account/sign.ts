










import crypto from 'node:crypto'

export interface DeviceSignHeaders {
  'X-Device-Fp': string
  'X-Device-Ts': string
  'X-Device-Nonce': string
  'X-Device-Sign': string
}








export function deviceSignHeaders(
  deviceSecret: string,
  deviceFp: string,
  method: string,
  pathNoQuery: string,
): DeviceSignHeaders {
  const key = crypto.createHash('sha256').update(deviceSecret).digest('hex')
  const ts = String(Date.now())
  const nonce = crypto.randomUUID()
  const canon = [method.toUpperCase(), pathNoQuery, ts, nonce].join('\n')
  const sign = crypto.createHmac('sha256', key).update(canon).digest('hex')
  return {
    'X-Device-Fp': deviceFp,
    'X-Device-Ts': ts,
    'X-Device-Nonce': nonce,
    'X-Device-Sign': sign,
  }
}









export function looksLikeSignatureError(message: string): boolean {
  return /签名|nonce|时间戳|timestamp|请求时间|鉴权/i.test(message)
}
