/**
 * 语音能力的状态与调用。
 *
 * ## 为什么单独一个 store，不塞进 chatStore
 *
 * 语音是**跨会话**的能力：单聊、群聊、独立窗口共用同一支麦克风，也共用同一份
 * "模型准备好没有"。而 chatStore 本来就很长，语音这条支线与"对话"本身没有关系，
 * 混进去只会让两边都更难改。
 *
 * ## 为什么能力探测结果要缓存
 *
 * `/v1/voice/status` 要问核心。而 `available`（模型文件在不在）在一次安装里是**不会变**的
 * —— 会变的是 `loaded`（首次载入约 1 秒），那个不需要界面提前知道。
 * 所以问一次就记住；用户在设置页改了语音相关配置后可以显式 `refresh()`。
 */

import { create } from 'zustand'

import { float32ToBase64 } from '@/services/voiceCapture'
import { getApi } from '@/stores/appStore'

export interface VoiceAvailability {
  /** 本地语音识别（SenseVoice）是否可用。唤醒判定也走它，所以这一个就够。 */
  asr: boolean
}

interface VoiceState {
  /** 核心侧语音能力；`null` = 还没问过。 */
  availability: VoiceAvailability | null
  /** 正在识别。界面上必须显示出来 —— 说完到出文字之间若是一片空白，用户会以为没听清。 */
  transcribing: boolean
  refresh: () => Promise<void>
  /**
   * 识别一段波形，返回文字（可能是空串 = 没听到人说话）。
   *
   * 失败**原样抛出**：不同调用场景要给的提示不一样（单聊 vs 群聊 vs 设置页试听），
   * 在这个层统一成一句话反而会丢失上下文。
   */
  transcribe: (samples: Float32Array, sampleRate: number) => Promise<string>
}

export const useVoiceStore = create<VoiceState>((set, get) => ({
  availability: null,
  transcribing: false,

  refresh: async () => {
    if (get().availability) return // 装好的模型不会凭空消失，问一次就够
    try {
      const status = await getApi().voiceStatus()
      set({ availability: { asr: status.asr.available } })
    } catch {
      // 核心还没起来时问不到 —— 那是正常启动过程，不要弹错误打扰用户。
      // 留成 null，下次进输入框时会再问一次。
    }
  },

  transcribe: async (samples, sampleRate) => {
    set({ transcribing: true })
    try {
      const result = await getApi().voiceAsr(float32ToBase64(samples), sampleRate)
      return result.text.trim()
    } finally {
      set({ transcribing: false })
    }
  },
}))
