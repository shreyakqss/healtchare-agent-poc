/**
 * Microphone capture for the patient portal.
 *
 * The browser does the encoding: it records with `MediaRecorder`, then decodes
 * and re-encodes to 16 kHz mono 16-bit WAV before upload. That is the one
 * format Moonshine wants, and doing it here means the backend needs no audio
 * codec at all — the standard library's `wave` module reads what arrives.
 *
 * No dependency: `AudioContext` already decodes whatever `MediaRecorder`
 * produced (webm/opus on Chrome, mp4/aac on Safari), and a WAV header is 44
 * bytes of `DataView` writes.
 */

const TARGET_RATE = 16_000;

export class MicrophoneError extends Error {
  constructor(
    message: string,
    /** True when the patient can fix it by granting permission. */
    readonly permission: boolean = false,
  ) {
    super(message);
  }
}

export type Recording = {
  /** Stop, release the microphone, and return 16 kHz mono WAV. */
  stop: () => Promise<Blob>;
  /** Abandon the recording and release the microphone. */
  cancel: () => void;
  /** Current input loudness, 0–1, for the level meter. */
  level: () => number;
  /** `count` real frequency-band magnitudes, 0–1, for the waveform bars. */
  bands: (count: number) => number[];
};

/** Ask for the microphone and start capturing. */
export async function record(): Promise<Recording> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new MicrophoneError(
      "This browser cannot access a microphone. You can still type your answers.",
    );
  }

  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
  } catch (err) {
    const name = (err as DOMException)?.name;
    if (name === "NotAllowedError" || name === "SecurityError") {
      throw new MicrophoneError(
        "Microphone access was blocked. Allow it in your browser, or type your answer instead.",
        true,
      );
    }
    if (name === "NotFoundError" || name === "DevicesNotFoundError") {
      throw new MicrophoneError(
        "No microphone was found. You can still type your answers.",
      );
    }
    throw new MicrophoneError(
      "The microphone could not be started. You can still type your answers.",
    );
  }

  const context = new AudioContext();
  const analyser = context.createAnalyser();
  analyser.fftSize = 512;
  context.createMediaStreamSource(stream).connect(analyser);
  const meter = new Uint8Array(analyser.frequencyBinCount);

  const recorder = new MediaRecorder(stream);
  const chunks: Blob[] = [];
  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  };
  recorder.start();

  const release = () => {
    stream.getTracks().forEach((track) => track.stop());
    void context.close();
  };

  return {
    level() {
      analyser.getByteTimeDomainData(meter);
      let sum = 0;
      for (const sample of meter) {
        const centred = (sample - 128) / 128;
        sum += centred * centred;
      }
      // RMS is small for speech; scale so normal talking fills the meter.
      return Math.min(1, Math.sqrt(sum / meter.length) * 4);
    },

    bands(count) {
      analyser.getByteFrequencyData(meter);
      // Speech energy sits low in the spectrum, so only the bottom half of the
      // bins is worth drawing — the rest would be permanently flat.
      const usable = Math.floor(meter.length / 2);
      const width = Math.max(1, Math.floor(usable / count));
      return Array.from({ length: count }, (_, i) => {
        let sum = 0;
        for (let j = 0; j < width; j += 1) sum += meter[i * width + j] ?? 0;
        return Math.min(1, sum / width / 200);
      });
    },

    cancel() {
      if (recorder.state !== "inactive") recorder.stop();
      release();
    },

    async stop() {
      const finished = new Promise<void>((resolve) => {
        recorder.onstop = () => resolve();
      });
      if (recorder.state !== "inactive") recorder.stop();
      await finished;
      release();

      const encoded = await new Blob(chunks, { type: recorder.mimeType }).arrayBuffer();
      if (encoded.byteLength === 0) {
        throw new MicrophoneError("Nothing was recorded. Try again.");
      }

      // A fresh context: the capture one is closed, and decoding needs no
      // particular sample rate — the resample below handles it either way.
      const decoder = new AudioContext();
      try {
        const buffer = await decoder.decodeAudioData(encoded);
        return toWav(downmix(buffer), TARGET_RATE);
      } finally {
        void decoder.close();
      }
    },
  };
}

/**
 * Sequential playback of a reply that is still being written.
 *
 * Segments arrive from the turn stream faster than they can be heard, so they
 * queue. Synthesis of a segment starts the moment it is pushed while playback
 * waits its turn — that overlap is the whole point: segment two is being
 * generated while segment one is being spoken. Order is preserved by chaining
 * the *playback*, not the fetches.
 *
 * `stop()` is the interrupt: it silences what is playing and drops everything
 * queued behind it. Nothing about the conversation is touched — the text is
 * already on screen and the turn is already stored.
 */
export type SpeechQueue = {
  push: (text: string, index: number) => void;
  stop: () => void;
  /** Resolves when everything pushed so far has finished playing. */
  idle: () => Promise<void>;
};

export function speechQueue(
  synthesise: (text: string, index: number) => Promise<Blob>,
  onFail: (error: unknown) => void,
): SpeechQueue {
  let chain = Promise.resolve();
  let stopped = false;
  let playing: HTMLAudioElement | null = null;

  return {
    push(text, index) {
      // Caught here so a failed segment cannot become an unhandled rejection
      // when the queue is stopped before its turn to play comes round.
      const pending = synthesise(text, index).catch((error) => {
        onFail(error);
        return null;
      });

      chain = chain.then(async () => {
        const blob = await pending;
        if (!blob || stopped) return;

        const url = URL.createObjectURL(blob);
        const element = new Audio(url);
        playing = element;
        try {
          await new Promise<void>((resolve, reject) => {
            element.onended = () => resolve();
            element.onerror = () => reject(new Error("The reply could not be played."));
            element.play().catch(reject);
          });
        } catch (error) {
          onFail(error);
        } finally {
          URL.revokeObjectURL(url);
          if (playing === element) playing = null;
        }
      });
    },

    stop() {
      stopped = true;
      playing?.pause();
      playing = null;
    },

    idle() {
      return chain;
    },
  };
}

/** Average the channels and resample to 16 kHz. */
function downmix(buffer: AudioBuffer): Float32Array {
  const channels = Array.from({ length: buffer.numberOfChannels }, (_, i) =>
    buffer.getChannelData(i),
  );
  const mono = new Float32Array(buffer.length);
  for (let i = 0; i < buffer.length; i += 1) {
    let sum = 0;
    for (const channel of channels) sum += channel[i];
    mono[i] = sum / channels.length;
  }

  if (buffer.sampleRate === TARGET_RATE) return mono;

  // Linear resample. Speech at 16 kHz does not need a windowed filter, and the
  // model was trained on ordinary microphone audio.
  const ratio = buffer.sampleRate / TARGET_RATE;
  const out = new Float32Array(Math.floor(mono.length / ratio));
  for (let i = 0; i < out.length; i += 1) {
    const at = i * ratio;
    const low = Math.floor(at);
    const high = Math.min(low + 1, mono.length - 1);
    out[i] = mono[low] + (mono[high] - mono[low]) * (at - low);
  }
  return out;
}

/** Float samples in [-1, 1] to a 16-bit PCM WAV blob. */
function toWav(samples: Float32Array, sampleRate: number): Blob {
  const bytes = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(bytes);
  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };

  ascii(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true); // PCM header size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  ascii(36, "data");
  view.setUint32(40, samples.length * 2, true);

  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, clamped * 32767, true);
  }
  return new Blob([bytes], { type: "audio/wav" });
}
