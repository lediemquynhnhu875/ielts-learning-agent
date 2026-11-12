"""Compare an existing synthesized WAV with a script without another TTS call."""

import argparse
import json
from pathlib import Path

from ..core.config import Settings
from ..infrastructure.azure_speech import MAX_AUDIO_BYTES, AzureSpeech, SpeechError
from ..infrastructure.azure_stt import AzureSTT
from .verification import ListeningAudioVerifier


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True, help="Existing Azure PCM WAV")
    parser.add_argument("--script", type=Path, required=True, help="UTF-8 original script, including optional speaker labels")
    parser.add_argument("--output", type=Path, help="Save comparison JSON here instead of stdout")
    args = parser.parse_args()
    try:
        if args.output and args.output.resolve() in {args.audio.resolve(), args.script.resolve()}:
            raise SpeechError(422, "invalid_verification_output", "Report output must not overwrite the audio or reference file")
        if args.audio.stat().st_size > MAX_AUDIO_BYTES or args.script.stat().st_size > 48_000:
            raise SpeechError(422, "verification_input_too_large", "Audio or reference file exceeds verification limits")
        settings = Settings.from_env()
        verifier = ListeningAudioVerifier(AzureSpeech(settings), AzureSTT(settings))
        result = verifier.verify_audio(args.script.read_text(encoding="utf-8-sig"), args.audio.read_bytes())
        body = result.model_dump_json(indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(body + "\n", encoding="utf-8")
            print(json.dumps({"report_path": str(args.output), "normalized_match": result.comparison.normalized_match,
                              "word_error_rate": result.comparison.word_error_rate}))
        else:
            print(json.dumps(result.model_dump(), ensure_ascii=True, indent=2))
    except SpeechError as error:
        print(json.dumps({"error": error.code, "message": str(error)}))
        return 1
    except (OSError, UnicodeError):
        print(json.dumps({"error": "verification_file_error", "message": "Cannot read input or write the verification report"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
