"""Run the recorded samples and preserve transcripts, timestamps and timings."""

import argparse
import csv
import difflib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import time

from ielts_agent.agents.speaking.test_whisper import fluency_metrics, groq_stt_model, transcribe_groq, transcribe_local


ROOT = Path(__file__).resolve().parents[4]


def tokens(text):
    return re.findall(r"[a-z]+(?:'[a-z]+)?|\d+", text.lower())


def read_scripts():
    source = (ROOT / "docs" / "speaking" / "stt-samples.md").read_text()
    scripts = {}
    for match in re.finditer(
        r"## Sample (\d+)[^\n]*\n.*?\*\*Nội dung đọc\*\*\s*\n(.*?)(?=\n\*\*)",
        source,
        re.DOTALL,
    ):
        scripts[f"sample-{int(match[1]):02d}"] = re.sub(
            r"\[pause \d+s\]", "", match[2]
        ).strip()
    if len(scripts) != 10:
        raise ValueError(f"Expected 10 sample scripts, found {len(scripts)}")
    return scripts


def script_differences(script, transcript):
    expected, actual = tokens(script), tokens(transcript)
    matcher = difflib.SequenceMatcher(None, expected, actual, autojunk=False)
    return [
        {"type": tag, "script": " ".join(expected[a:b]),
         "transcript": " ".join(actual[c:d])}
        for tag, a, b, c, d in matcher.get_opcodes() if tag != "equal"
    ]


def save_report(output, data):
    (output / "results.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    )
    fields = ["sample", "backend", "keep_fillers", "audio_seconds",
              "processing_seconds", "real_time_factor", "so_tu",
              "toc_do_tu_moi_phut", "so_lan_ngung", "so_tu_dem", "timestamps_available", "status"]
    with (output / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in data["results"]:
            row = {key: result.get(key, "") for key in fields}
            row.update({key: result.get("fluency", {}).get(key, "")
                        for key in fields if key.startswith("so_") or key.startswith("toc_")})
            writer.writerow(row)
    lines = ["# STT benchmark", "",
             "Reference: recording scripts, NOT verified audio transcripts. Differences may come from the speaker or STT. No ground-truth WER is claimed.",
             "", "Timings exclude model loading/download. The first inference may include warm-up. CPU batch timings are not production latency.",
             "", "Pause/filler metrics are inferred from recognized words, not independently verified audio measurements. Repeats count adjacent identical words only. The existing filler heuristic counts every 'like', including ordinary verb/preposition uses; it may miss spellings such as 'hmmm'.",
             "", f"Model loading: {data.get('model_load_seconds', 'N/A')} seconds.",
             "", "| Sample | Backend | Fillers prompt | Audio (s) | Processing (s) | RTF | Filler count | Pauses | Timestamps |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for result in data["results"]:
        if result["status"] != "ok":
            lines.extend(["", f"ERROR: {result['sample']} / {result['backend']}: {result['error']}"])
            continue
        metrics = result["fluency"]
        lines.append(f"| {result['sample']} | {result['backend']} | {result['keep_fillers']} | {result['audio_seconds']} | {result['processing_seconds']} | {result['real_time_factor']} | {metrics.get('so_tu_dem', 'N/A')} | {metrics.get('so_lan_ngung', 'N/A')} | {result.get('timestamps_available', bool(result['words']))} |")
    for result in data["results"]:
        lines.extend(["", f"## {result['sample']} / {result['backend']} / keep_fillers={result['keep_fillers']}", ""])
        if result["status"] != "ok":
            lines.append(result["error"])
            continue
        lines.extend([result["transcript"], "", "Script differences:", ""])
        if result.get("timestamp_error"):
            lines.extend([f"Timestamp extraction failed: {result['timestamp_error']}. Retried without word timestamps; fluency metrics unavailable. Processing time includes both attempts.", ""])
        for change in result["script_differences"]:
            lines.append(f"- {change['type']}: `{change['script']}` -> `{change['transcript']}`")
        if not result["script_differences"]:
            lines.append("No differences after case/punctuation normalization.")
    (output / "report.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["local", "groq"], default="local")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "speaking" / "stt-results" / "local")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    model_directory = ROOT / ".cache" / "whisper-large-v3-turbo"
    if args.download_only:
        from huggingface_hub import snapshot_download
        snapshot_download(
            "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
            local_dir=model_directory,
            allow_patterns=["config.json", "model.bin", "tokenizer.json",
                            "preprocessor_config.json", "vocabulary.*"],
        )
        print(f"Model downloaded: {model_directory}", flush=True)
        return
    if args.backend == "groq" and not os.environ.get("GROQ_API_KEY"):
        raise SystemExit("GROQ_API_KEY is not configured; no audio was uploaded.")
    scripts = read_scripts()
    samples = sorted((ROOT / "audio-sample").glob("sample-*.m4a"))
    if len(samples) != 10 or {p.stem for p in samples} != set(scripts):
        raise SystemExit("Expected exactly the 10 named sample recordings.")
    from faster_whisper.audio import decode_audio
    args.output.mkdir(parents=True, exist_ok=True)
    data = {"backend": args.backend, "model": "large-v3-turbo" if args.backend == "local" else groq_stt_model(),
            "platform": platform.platform(), "python": platform.python_version(),
            "reference_type": "unverified recording script",
            "packages": {name: importlib.metadata.version(name)
                         for name in ["faster-whisper", "ctranslate2", "groq", "av"]},
            "results": []}
    if args.retry_failed:
        data = json.loads((args.output / "results.json").read_text())
        if data["backend"] != args.backend:
            raise SystemExit("Existing results are from a different backend.")
        data["packages"]["av"] = importlib.metadata.version("av")
    model = None
    if args.backend == "local":
        from faster_whisper import WhisperModel
        print("Loading local large-v3-turbo (CPU int8, 4 threads)...", flush=True)
        started = time.perf_counter()
        model = WhisperModel(str(model_directory), device="cpu", compute_type="int8", cpu_threads=4)
        data["model_load_seconds"] = round(time.perf_counter() - started, 3)
        data["settings"] = {"device": "cpu", "compute_type": "int8", "cpu_threads": 4,
                            "language": None, "task": "transcribe", "multilingual": True,
                            "temperature": 0, "vad_filter": False}
    save_report(args.output, data)
    for path in samples:
        audio_seconds = len(decode_audio(str(path), sampling_rate=16000)) / 16000
        for keep_fillers in [False, True]:
            existing = next((r for r in data["results"]
                             if r["sample"] == path.stem and r["keep_fillers"] == keep_fillers), None)
            if args.retry_failed and existing and existing["status"] == "ok":
                continue
            print(f"Running {path.name}, keep_fillers={keep_fillers}, audio={audio_seconds:.1f}s", flush=True)
            result = {"sample": path.stem, "backend": args.backend,
                      "transcription_policy": "original_language_context_v2",
                      "model": "large-v3-turbo" if args.backend == "local" else groq_stt_model(),
                      "keep_fillers": keep_fillers, "audio_seconds": round(audio_seconds, 3)}
            started = time.perf_counter()
            try:
                if args.backend == "local":
                    try:
                        transcript, words = transcribe_local(str(path), keep_fillers, model=model)
                    except IndexError as error:
                        if "boolean index did not match" not in str(error):
                            raise
                        result["timestamp_error"] = str(error)
                        transcript, words = transcribe_local(
                            str(path), keep_fillers, model=model, word_timestamps=False
                        )
                else:
                    transcript, words = transcribe_groq(str(path), keep_fillers)
                elapsed = time.perf_counter() - started
                result.update(status="ok", processing_seconds=round(elapsed, 3),
                              timestamps_available=bool(words),
                              real_time_factor=round(elapsed / audio_seconds, 3),
                              transcript=transcript, words=words, fluency=fluency_metrics(words),
                              script=scripts[path.stem],
                              script_differences=script_differences(scripts[path.stem], transcript))
                print(f"Done in {elapsed:.1f}s: {transcript}", flush=True)
            except Exception as error:
                result.update(status="error", error=str(error),
                              processing_seconds=round(time.perf_counter() - started, 3))
                print(f"Failed: {error}", flush=True)
            if args.retry_failed and existing:
                result["previous_attempt"] = existing
                data["results"][data["results"].index(existing)] = result
            else:
                data["results"].append(result)
            save_report(args.output, data)
    failures = sum(r["status"] != "ok" for r in data["results"])
    print(f"Finished {len(data['results'])} runs; {failures} failed. Report: {args.output / 'report.md'}", flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
