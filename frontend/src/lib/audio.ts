export function float32ToPcm16(input: Float32Array, inputRate: number, outputRate = 16000): ArrayBuffer {
  const ratio = inputRate / outputRate
  const outputLength = Math.floor(input.length / ratio)
  const output = new Int16Array(outputLength)
  for (let index = 0; index < outputLength; index += 1) {
    const start = Math.floor(index * ratio)
    const end = Math.min(Math.floor((index + 1) * ratio), input.length)
    let sum = 0
    for (let source = start; source < end; source += 1) sum += input[source]
    const sample = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)))
    output[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
  }
  return output.buffer
}

export function rmsLevel(input: Float32Array): number {
  let energy = 0
  for (const sample of input) energy += sample * sample
  return Math.min(1, Math.sqrt(energy / input.length) * 3.5)
}

export function base64ToBytes(value: string): Uint8Array {
  const raw = atob(value)
  const bytes = new Uint8Array(raw.length)
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index)
  return bytes
}
