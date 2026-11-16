// Copies the microphone's raw samples to the page, which resamples them to 16 kHz for live transcription.
class PcmTap extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor('pcm-tap', PcmTap);
