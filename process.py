import numpy as np

try:
    from essentia.standard import (
        MonoLoader,
        FrameGenerator,
        Windowing,
        Spectrum,
        OnsetDetection,
        Onsets,
        BeatTrackerMultiFeature,
        Loudness,
    )
except ImportError as e:
    raise ImportError(
        "Essentia failed to import. Install with: pip install essentia"
    ) from e


# ------------------ Time utils ------------------

def format_timestamp(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds - int(seconds)) * 1000)
    return f"{minutes:02d}:{secs:02d}:{milliseconds:03d}"


def seconds_to_timecode(seconds, fps=30):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    frames = int((seconds % 1) * fps)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"


# ------------------ Core logic ------------------

def detect_beats(audio):
    tracker = BeatTrackerMultiFeature()
    beats, confidence = tracker(audio)
    return [float(b) for b in beats]


def detect_onsets(audio, sample_rate=44100, sensitivity="low"):
    frame_size = 2048
    hop_size = 512

    window = Windowing(type="hann")
    spectrum_alg = Spectrum()
    odf = OnsetDetection(method="hfc")
    onset_picker = Onsets()

    odf_values = []
    for frame in FrameGenerator(
        audio, frameSize=frame_size, hopSize=hop_size, startFromZero=True
    ):
        windowed = window(frame)
        spectrum = spectrum_alg(windowed)
        odf_values.append(odf(spectrum, spectrum))

    odf_array = np.array(odf_values)
    if len(odf_array) > 0 and odf_array.max() > 0:
        odf_array = odf_array / odf_array.max()

        thresholds = {
            "very_low": 0.6,
            "low": 0.4,
            "medium": 0.2,
            "high": 0.1,
        }
        threshold = thresholds.get(sensitivity, 0.4)
        odf_array[odf_array < threshold] = 0

    odf_matrix = np.array([odf_array.tolist()])
    onset_times = onset_picker(odf_matrix, [hop_size / sample_rate])
    return [float(o) for o in onset_times]


def filter_by_loudness(audio, times, sample_rate=44100, percentile=70):
    frame_size = 4096
    hop_size = 2048

    loudness_alg = Loudness()
    loudness_values = []
    time_stamps = []

    for i, frame in enumerate(
        FrameGenerator(audio, frameSize=frame_size, hopSize=hop_size, startFromZero=True)
    ):
        loudness_values.append(loudness_alg(frame))
        time_stamps.append(i * hop_size / sample_rate)

    if not loudness_values:
        return []

    threshold = np.percentile(loudness_values, percentile)

    filtered = []
    for t in times:
        idx = min(range(len(time_stamps)), key=lambda i: abs(time_stamps[i] - t))
        if loudness_values[idx] >= threshold:
            filtered.append(t)

    return filtered


def smart_spacing(times, min_gap=0.5):
    if not times:
        return []
    spaced = [times[0]]
    for t in times[1:]:
        if t - spaced[-1] >= min_gap:
            spaced.append(t)
    return spaced


def snap_onsets_to_beats(beats, onsets, snap_threshold=0.08):
    snapped = set(beats)
    for onset in onsets:
        if not beats:
            snapped.add(onset)
            continue
        nearest_beat = min(beats, key=lambda b: abs(b - onset))
        if abs(nearest_beat - onset) <= snap_threshold:
            snapped.add(nearest_beat)
        else:
            snapped.add(onset)
    return sorted(snapped)


# ------------------ EDL ------------------

def create_edl_markers(times, output_file, fps=30):
    lines = ["TITLE: Timeline Markers", "FCM: NON-DROP FRAME", ""]
    for i, t in enumerate(times, 1):
        tc = seconds_to_timecode(t, fps)
        lines.append(f"{i:03d}  001      V     C        {tc} {tc} {tc} {tc}")
        lines.append(f"* FROM CLIP NAME: Marker {i}")
        lines.append(f"|M:{tc}|Drop {i}")
        lines.append("")
    with open(output_file, "w") as f:
        f.write("\n".join(lines))


# ------------------ Entry point ------------------

def process_audio_file(audio_path, out_txt, out_edl, fps=30,
                       sensitivity="low", loudness=70, min_gap=0.5,
                       beats_only=False, progress_callback=None):
    """Programmatic entry point. Returns dict with marker_count."""
    def report(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)

    report(5, "Loading audio…")
    audio = MonoLoader(filename=audio_path)()

    if beats_only:
        report(25, "Detecting beats…")
        markers = detect_beats(audio)
    else:
        report(20, "Detecting beats…")
        beats = detect_beats(audio)
        report(40, "Detecting onsets…")
        onsets = detect_onsets(audio, sensitivity=sensitivity)
        report(55, "Merging markers…")
        markers = snap_onsets_to_beats(beats, onsets, snap_threshold=0.08)

    report(65, "Filtering by loudness…")
    markers = filter_by_loudness(audio, markers, percentile=loudness)

    report(80, "Enforcing spacing…")
    markers = smart_spacing(markers, min_gap=min_gap)

    final = [round(t, 3) for t in markers]

    report(90, "Writing outputs…")
    with open(out_txt, "w") as f:
        for t in final:
            f.write(f"{t}\n")
    create_edl_markers(final, out_edl, fps)

    report(100, "Done")
    return {"marker_count": len(final)}