export interface SseEvent {
  done: boolean
  payload: unknown | null
}

export interface SseBufferResult {
  events: SseEvent[]
  remainder: string
}

export function consumeSseBuffer(buffer: string, flush = false): SseBufferResult {
  if (!buffer) {
    return { events: [], remainder: '' }
  }

  const frames = buffer.split('\n\n')
  const remainder = flush ? '' : (frames.pop() ?? '')
  const completeFrames = flush ? frames.filter(Boolean).concat(remainder ? [remainder] : []) : frames.filter(Boolean)
  const events = completeFrames.flatMap(parseSseFrame)

  return {
    events,
    remainder: flush ? '' : remainder,
  }
}

function parseSseFrame(frame: string): SseEvent[] {
  const payloadLines = frame
    .split('\n')
    .filter((line) => line.startsWith('data: '))
    .map((line) => line.slice(6))

  if (!payloadLines.length) {
    return []
  }

  const payloadText = payloadLines.join('\n')
  if (payloadText === '[DONE]') {
    return [{ done: true, payload: null }]
  }

  try {
    return [{ done: false, payload: JSON.parse(payloadText) }]
  } catch {
    return []
  }
}
