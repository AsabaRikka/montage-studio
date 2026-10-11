"""Local MDX instrumental estimation; residual is approximate voice/effects.

Model parameters verified against UVR's model_data.json by tail-MD5
55657dd70583b0fedfba5f67df11d711. No torch runtime is required.
"""
from pathlib import Path
import json
import numpy as np


NFFT, HOP, FRAMES, FREQ, COMPENSATE = 6144, 1024, 256, 3072, 1.022


def stft(audio):
    padded = np.pad(audio, ((0, 0), (NFFT//2, NFFT//2)), mode='reflect')
    frames = np.lib.stride_tricks.sliding_window_view(padded, NFFT, axis=1)[:, ::HOP]
    window = np.hanning(NFFT+1)[:-1].astype(np.float32)
    spec = np.fft.rfft(frames * window, axis=-1).transpose(0, 2, 1)
    # UVR order: left real, left imaginary, right real, right imaginary.
    return np.stack([spec[0].real, spec[0].imag, spec[1].real, spec[1].imag]).astype(np.float32)[:, :FREQ]


def istft(tensor, length):
    spec = np.zeros((2, NFFT//2+1, FRAMES), dtype=np.complex64)
    spec[0, :FREQ] = tensor[0] + 1j*tensor[1]
    spec[1, :FREQ] = tensor[2] + 1j*tensor[3]
    frames = np.fft.irfft(spec.transpose(0, 2, 1), n=NFFT, axis=-1).astype(np.float32)
    window = np.hanning(NFFT+1)[:-1].astype(np.float32)
    result = np.zeros((2, HOP*(FRAMES-1)+NFFT), np.float32)
    weight = np.zeros(result.shape[1], np.float32)
    for i in range(FRAMES):
        start = i*HOP
        result[:, start:start+NFFT] += frames[:, i]*window
        weight[start:start+NFFT] += window**2
    result /= np.maximum(weight, 1e-8)
    return result[:, NFFT//2:NFFT//2+length]


def separate(wav, output, model, report=None):
    import onnxruntime as ort
    from scipy.io import wavfile
    rate, audio = wavfile.read(wav)
    if rate != 44100:
        raise ValueError('分离输入须为44100Hz。')
    audio = audio.astype(np.float32)
    if audio.ndim == 1:
        audio = np.stack([audio, audio], axis=1)
    audio = audio[:, :2].T
    if not np.isfinite(audio).all():
        raise ValueError('音轨含无效采样。')
    peak = max(float(np.max(np.abs(audio))), 1e-6)
    normalized = audio/max(peak, 1.)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 3
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model), sess_options=options, providers=['CPUExecutionProvider'])
    chunk_size = HOP*(FRAMES-1)
    trim = NFFT//2
    useful = chunk_size-2*trim
    step = useful//2
    samples = audio.shape[1]
    mixed = np.zeros_like(audio)
    weights = np.zeros(samples, np.float32)
    blend = np.maximum(np.hanning(useful).astype(np.float32), 1e-3)
    padded = np.pad(normalized, ((0, 0), (trim, chunk_size)), mode='constant')
    for start in range(0, samples, step):
        chunk = padded[:, start:start+chunk_size]
        tensor = stft(chunk)[None]
        tensor[:, :, :3, :] = 0
        prediction = session.run(None, {session.get_inputs()[0].name: tensor})[0][0]
        instrumental = istft(prediction, chunk_size)[:, trim:trim+useful]
        end = min(samples, start+useful)
        n = end-start
        mixed[:, start:end] += instrumental[:, :n]*blend[:n]
        weights[start:end] += blend[:n]
    instrumental = mixed/np.maximum(weights, 1e-8)*COMPENSATE
    residual = (normalized-instrumental)*max(peak, 1.)
    if not np.isfinite(residual).all():
        raise ValueError('分离结果含无效采样。')
    wavfile.write(output, rate, residual.T.astype(np.float32))
    if report:
        Path(report).write_text(json.dumps(dict(samples=samples, rate=rate, seconds=samples/rate,
            peak=float(np.max(np.abs(residual))), model=Path(model).name)), encoding='utf-8')
