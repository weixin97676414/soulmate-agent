

















import { execFile } from 'node:child_process'
import os from 'node:os'

export interface DeviceInfo {
  
  machine_guid: string
  
  smbios_uuid: string
  
  board_serial: string
  
  cpu_id: string
  
  disk_serial: string
  
  macs: string[]
}





const PLACEHOLDER =
  /^(default string|to be filled by o\.e\.m\.?|none|null|nil|unknown|n\/a|not applicable|not specified|system serial number|base board serial number|invalid|0|o\.e\.m\.?|00000000-0000-0000-0000-000000000000|-+|\.+)$/i









const VIRTUAL_ADAPTER =
  /(virtual|vmware|vbox|virtualbox|hyper-?v|vethernet|loopback|bluetooth|tap|tun\b|wsl|docker|zerotier|tailscale|npcap|radmin|hamachi|vpn|wan miniport|wi-?fi direct|teredo|isatap|虚拟|回环|隧道|伪)/i

function clean(value: unknown): string {
  const trimmed = typeof value === 'string' ? value.trim() : ''
  return PLACEHOLDER.test(trimmed) ? '' : trimmed
}








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


function readMacs(): string[] {
  const found = new Set<string>()
  for (const [name, addresses] of Object.entries(os.networkInterfaces())) {
    if (VIRTUAL_ADAPTER.test(name)) continue
    for (const address of addresses ?? []) {
      
      if (address.internal) continue
      const mac = (address.mac ?? '').trim().toLowerCase()
      if (!mac || mac === '00:00:00:00:00:00' || mac === 'ff:ff:ff:ff:ff:ff') continue
      found.add(mac)
    }
  }
  
  
  return [...found].sort()
}







export function isDeviceUsable(info: DeviceInfo): boolean {
  return Boolean(info.machine_guid || info.smbios_uuid || info.board_serial)
}


let cached: DeviceInfo | null = null


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


export function resetDeviceInfoCache(): void {
  cached = null
}
