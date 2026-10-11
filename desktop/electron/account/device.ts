/**
 * 设备指纹采集（文档 §3）。
 *
 * 它是「这台机器是哪个账号」的唯一依据：重装客户端、换安装目录、甚至重装系统
 * （只要 `machine_guid` 还在）都要能认出旧账号。所以**每次启动都重采**，
 * 不做长期缓存 —— 缓存恰恰会在"换了网卡/换了主板"时给出一个错误的身份，
 * 而错误的身份意味着**又建一个新账号**。
 *
 * ## 三处刻意的取舍
 *
 * 1. **只用一次 PowerShell 拿四个 WMI 字段**。每个字段单起一次进程的话，首启要多等
 *    三次 PowerShell 冷启动（每次 1~2 秒），而这是后台流程 —— 用户看不到进度，
 *    只会觉得"应用启动变慢了"。
 * 2. **取不到就是空串，绝不用随机值兜底**。随机值会把同一台机器算成两台，
 *    后果是每次启动都新建一个账号（真的花钱），比"识别不出设备"严重得多。
 * 3. **主判据（machine_guid / smbios_uuid / board_serial）全空 = 账号功能不可用**，
 *    这时**不能**再去调账号接口：后端只会回 400，而重试一万次也一样。
 */
import { execFile } from 'node:child_process'
import os from 'node:os'

export interface DeviceInfo {
  /** 注册表 HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid */
  machine_guid: string
  /** WMI Win32_ComputerSystemProduct.UUID */
  smbios_uuid: string
  /** WMI Win32_BaseBoard.SerialNumber */
  board_serial: string
  /** WMI Win32_Processor.ProcessorId */
  cpu_id: string
  /** WMI Win32_DiskDrive.SerialNumber（系统盘） */
  disk_serial: string
  /** 物理网卡 MAC（已过滤虚拟网卡，小写、去重、排序） */
  macs: string[]
}

/**
 * 厂商占位值。这些值在成百上千台机器上**完全一样**，拿来当身份比空值更糟：
 * 空值会让后端说"认不出设备"，而占位值会把所有"Default string"的机器算成同一台。
 */
const PLACEHOLDER =
  /^(default string|to be filled by o\.e\.m\.?|none|null|nil|unknown|n\/a|not applicable|not specified|system serial number|base board serial number|invalid|0|o\.e\.m\.?|00000000-0000-0000-0000-000000000000|-+|\.+)$/i

/**
 * 虚拟网卡的识别词。
 *
 * 只能靠名字过滤：Node 的 `os.networkInterfaces()` 在 Windows 上给的就是适配器
 * 友好名（Node 内部走 GetAdaptersAddresses 的 FriendlyName）。MAC 不是主判据，
 * 所以这里**宁可漏掉一个真实网卡，也不要收进来一个虚拟的** —— 虚拟网卡
 * （VPN、WSL、Docker、虚拟机）恰恰是最容易在重装后变化的那一批。
 */
const VIRTUAL_ADAPTER =
  /(virtual|vmware|vbox|virtualbox|hyper-?v|vethernet|loopback|bluetooth|tap|tun\b|wsl|docker|zerotier|tailscale|npcap|radmin|hamachi|vpn|wan miniport|wi-?fi direct|teredo|isatap|虚拟|回环|隧道|伪)/i

function clean(value: unknown): string {
  const trimmed = typeof value === 'string' ? value.trim() : ''
  return PLACEHOLDER.test(trimmed) ? '' : trimmed
}

/**
 * 起一个 PowerShell 拿输出。
 *
 * 用 `execFile`（异步）而不是 `execFileSync`：同步版本会把主进程连同界面一起卡住
 * 最多几秒，而这几秒恰恰发生在用户刚双击图标的时候。
 * 任何失败都降级成空串 —— 设备字段缺一个不影响其它字段，抛错却会让整个首启中断。
 */
function runPowerShell(script: string, timeoutMs: number): Promise<string> {
  return new Promise((resolve) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
      { timeout: timeoutMs, windowsHide: true, maxBuffer: 1 << 20 },
      (error, stdout) => resolve(error ? '' : stdout),
    )
  })
}

/** 读注册表中的 MachineGuid。这是最稳的一条：重装系统之外它几乎不会变。 */
async function readMachineGuid(): Promise<string> {
  const output = await runPowerShell(
    '(Get-ItemProperty -Path "HKLM:\\SOFTWARE\\Microsoft\\Cryptography" -Name MachineGuid ' +
      '-ErrorAction SilentlyContinue).MachineGuid',
    4000,
  )
  return clean(output)
}

interface WmiPayload {
  smbios_uuid?: string
  board_serial?: string
  cpu_id?: string
  disk_serial?: string
}

/**
 * 一次 PowerShell 拿全四个 WMI 字段，输出压缩 JSON。
 *
 * `Get-CimInstance` 一次只能查一个类，所以在脚本里依次查四次、最后合成一个对象；
 * 关键是**只付一次进程启动的代价**。系统盘按 `Index -eq 0` 取（与
 * `Win32_DiskDrive` 的常见约定一致）。
 */
async function readWmiFields(): Promise<WmiPayload> {
  const script = [
    '$ErrorActionPreference = "SilentlyContinue"',
    '$cs = Get-CimInstance Win32_ComputerSystemProduct | Select-Object -First 1',
    '$bb = Get-CimInstance Win32_BaseBoard | Select-Object -First 1',
    '$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1',
    '$disk = Get-CimInstance Win32_DiskDrive | Where-Object { $_.Index -eq 0 } | Select-Object -First 1',
    '@{ smbios_uuid = $cs.UUID; board_serial = $bb.SerialNumber; cpu_id = $cpu.ProcessorId; ' +
      'disk_serial = $disk.SerialNumber } | ConvertTo-Json -Compress',
  ].join('; ')
  const output = await runPowerShell(script, 8000)
  const start = output.indexOf('{')
  if (start < 0) return {}
  try {
    return JSON.parse(output.slice(start).trim()) as WmiPayload
  } catch {
    return {}
  }
}

/** 物理网卡 MAC。 */
function readMacs(): string[] {
  const found = new Set<string>()
  for (const [name, addresses] of Object.entries(os.networkInterfaces())) {
    if (VIRTUAL_ADAPTER.test(name)) continue
    for (const address of addresses ?? []) {
      // internal 是回环；mac 为全 0 是"没拿到"而不是"值就是它"
      if (address.internal) continue
      const mac = (address.mac ?? '').trim().toLowerCase()
      if (!mac || mac === '00:00:00:00:00:00' || mac === 'ff:ff:ff:ff:ff:ff') continue
      found.add(mac)
    }
  }
  // 排序：同一台机器在不同次启动里的网卡枚举顺序可能不同，
  // 顺序一变指纹就变 —— 那等于每次启动都换了个设备
  return [...found].sort()
}

/**
 * 主判据（文档 §3）：三个里至少一个非空，否则账号功能不可用。
 *
 * MAC 与 cpu_id / disk_serial **不参与**这个判断：虚拟网卡过滤、CPU 型号字段在
 * 部分机器上恒为占位值，拿它们当判据会把"能用的机器"误判成不能用。
 */
export function isDeviceUsable(info: DeviceInfo): boolean {
  return Boolean(info.machine_guid || info.smbios_uuid || info.board_serial)
}

/** 进程内缓存：一次启动里多处都要用设备信息，没必要重复起进程。 */
let cached: DeviceInfo | null = null

/** 采集设备指纹。首次调用会起两次进程（注册表 + WMI），之后走缓存。 */
export async function collectDeviceInfo(force = false): Promise<DeviceInfo> {
  if (cached && !force) return cached
  const [machineGuid, wmi] = await Promise.all([readMachineGuid(), readWmiFields()])
  cached = {
    machine_guid: machineGuid,
    smbios_uuid: clean(wmi.smbios_uuid),
    board_serial: clean(wmi.board_serial),
    cpu_id: clean(wmi.cpu_id),
    disk_serial: clean(wmi.disk_serial),
    macs: readMacs(),
  }
  return cached
}

/** 供测试 / 排查用：清掉进程内缓存，下次调用重新采集。 */
export function resetDeviceInfoCache(): void {
  cached = null
}
