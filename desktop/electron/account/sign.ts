/**
 * 设备签名（文档 §4.2）。
 *
 * 改密码、改账号名、以及**没有会话时**读账号信息都靠它。文档给了一段可复制的
 * JS 实现，这里逐字对齐它的三个坑 —— 这三个坑任意一个踩中，现象都是
 * "有时候能改有时候不能"，而错误信息里只有一句"签名无效"：
 *
 * 1. **签名里的路径必须去掉查询串**。账号放在 `?account=` 里，但它不参与签名；
 * 2. **请求体不参与签名**（后端不校验 body，签名只覆盖 method + path + ts + nonce）；
 * 3. **密钥是 `sha256_hex(device_secret)`**，不是 device_secret 本身。
 */
import crypto from 'node:crypto'

export interface DeviceSignHeaders {
  'X-Device-Fp': string
  'X-Device-Ts': string
  'X-Device-Nonce': string
  'X-Device-Sign': string
}

/**
 * 生成四个签名头。
 *
 * `pathNoQuery` 必须是**去掉 `?...` 的路径**，如 `/api/agent/v1/account`。
 * 每次调用都用新的 `ts` 与 `nonce` —— nonce 在 5 分钟内不可复用（复用得 401），
 * 所以这里不做任何缓存。
 */
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

/**
 * 这个 401 是不是"签名本身有问题"（而不是"密码不对"）。
 *
 * 为什么要区分：签名类失败要**重新生成 ts + nonce 重试一次**（ts 偏差或 nonce
 * 复用都是一过性的），而密码错误重试一百次也没用。两种都是 401，只能看文案。
 * 靠文案判断听起来脆，但比"一律重试一次"好：后者会在用户输错密码时多发一次
 * 请求，还会把"密码错误"拖慢一拍。
 */
export function looksLikeSignatureError(message: string): boolean {
  return /签名|nonce|时间戳|timestamp|请求时间|鉴权/i.test(message)
}
