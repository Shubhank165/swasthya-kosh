class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.ratio = sampleRate / this.targetRate;
    this.position = 0;
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel || channel.length === 0) return true;

    let energy = 0;
    for (const sample of channel) energy += sample * sample;
    const rms = Math.sqrt(energy / channel.length);

    const output = [];
    while (this.position < channel.length) {
      const left = Math.floor(this.position);
      const right = Math.min(left + 1, channel.length - 1);
      const fraction = this.position - left;
      const value = channel[left] + (channel[right] - channel[left]) * fraction;
      output.push(Math.max(-1, Math.min(1, value)));
      this.position += this.ratio;
    }
    this.position -= channel.length;

    const pcm = new Int16Array(output.length);
    for (let i = 0; i < output.length; i += 1) {
      pcm[i] = output[i] < 0 ? output[i] * 32768 : output[i] * 32767;
    }
    this.port.postMessage({ pcm, rms }, [pcm.buffer]);
    return true;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);

