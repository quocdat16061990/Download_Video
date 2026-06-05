from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from subprocess import run
from typing import Any
from urllib.parse import urljoin

import imageio_ffmpeg
import requests


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


ENV_PATH = Path(".env")


HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9,vi;q=0.8",
    "cache-control": "no-cache",
    "origin": "https://app.voomly.com",
    "pragma": "no-cache",
    "referer": "https://app.voomly.com/",
    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
}


def load_dotenv(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_segments(playlist_text: str) -> list[str]:
    return [line.strip() for line in playlist_text.splitlines() if line.strip() and not line.startswith("#")]


def resolve_media_playlist(session: requests.Session, playlist_url: str) -> tuple[str, str]:
    response = session.get(playlist_url, timeout=30)
    response.raise_for_status()
    playlist_text = response.text

    if "#EXT-X-STREAM-INF" not in playlist_text:
        return playlist_url, playlist_text

    for line in playlist_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        child_url = urljoin(playlist_url, line)
        child_response = session.get(child_url, timeout=30)
        child_response.raise_for_status()
        return child_url, child_response.text

    raise RuntimeError("No child media playlist found in master playlist.")


def download_hls(playlist_url: str, output_path: Path) -> None:
    session = requests.Session()
    session.headers.update(HEADERS)

    playlist_url, playlist_text = resolve_media_playlist(session, playlist_url)
    if "#EXT-X-KEY" in playlist_text:
        raise RuntimeError("Playlist uses encryption; this script does not handle encrypted HLS.")

    segments = parse_segments(playlist_text)
    if not segments:
        raise RuntimeError("No media segments found in playlist.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as output_file:
        total = len(segments)
        for index, segment in enumerate(segments, start=1):
            segment_url = urljoin(playlist_url, segment)
            segment_response = session.get(segment_url, timeout=30)
            segment_response.raise_for_status()
            output_file.write(segment_response.content)
            print(f"[{index}/{total}] {segment}")


def remux_to_mp4(input_path: Path, output_path: Path) -> None:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = run(
        [ffmpeg_exe, "-y", "-i", str(input_path), "-c", "copy", str(output_path)],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or "ffmpeg remux failed")


def download_to_path(playlist_url: str, output_path: Path) -> None:
    if output_path.suffix.lower() == ".mp4":
        temp_output = output_path.with_suffix(".download.ts")
        download_hls(playlist_url, temp_output)
        remux_to_mp4(temp_output, output_path)
        temp_output.unlink(missing_ok=True)
    else:
        download_hls(playlist_url, output_path)

    print(f"Saved to {output_path.resolve()}")


def build_api_headers(token: str) -> dict[str, str]:
    headers = dict(HEADERS)
    headers["accept"] = "application/json"
    headers["authorization"] = f"Bearer {token}"
    headers["funnel-version"] = "2"
    headers["player-version"] = "2"
    headers["voomly-frontend-version"] = "0.0.173"
    return headers


def sanitize_filename(value: str) -> str:
    value = re.sub(r'[<>:"/\\\\|?*]', "_", value).strip()
    value = re.sub(r"\s+", " ", value)
    return value[:180] or "video"


def fetch_spotlight(spotlight_id: str, token: str) -> dict[str, Any]:
    response = requests.get(
        f"https://api.voomly.com/spotlights/{spotlight_id}",
        headers=build_api_headers(token),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def collect_video_entries(data: dict[str, Any]) -> list[dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}

    def register(video_id: str, lesson_name: str | None, path: str) -> None:
        current = entries.setdefault(
            video_id,
            {"video_id": video_id, "lesson_name": lesson_name or "", "path": path},
        )
        if not current["lesson_name"] and lesson_name:
            current["lesson_name"] = lesson_name

    def walk(node: Any, path: str = "root", lesson_name: str | None = None) -> None:
        if isinstance(node, dict):
            current_lesson_name = lesson_name
            if node.get("type") == "lesson" and isinstance(node.get("name"), str):
                current_lesson_name = node["name"]

            if (
                isinstance(node.get("video"), dict)
                and isinstance(node["video"].get("id"), str)
                and node["video"].get("enabled", True)
            ):
                register(node["video"]["id"], current_lesson_name, f"{path}.video")

            if node.get("type") == "voomly" and isinstance(node.get("id"), str):
                register(node["id"], current_lesson_name, path)

            for key, value in node.items():
                walk(value, f"{path}.{key}", current_lesson_name)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]", lesson_name)

    walk(data)
    return list(entries.values())


def fetch_video_metadata(video_id: str, token: str) -> dict[str, Any]:
    response = requests.get(
        f"https://api.voomly.com/videos/{video_id}/voomly",
        headers=build_api_headers(token),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def choose_quality_url(metadata: dict[str, Any], preferred_label: str) -> tuple[str, str]:
    quality_options = metadata.get("qualityOptions") or []
    preferred = preferred_label.lower()

    for option in quality_options:
        label = str(option.get("label", "")).lower()
        hls_url = option.get("hlsUrl")
        if label == preferred and isinstance(hls_url, str):
            return hls_url, str(option.get("label", preferred_label))

    best_option: dict[str, Any] | None = None
    for option in quality_options:
        if not isinstance(option.get("hlsUrl"), str):
            continue
        if best_option is None:
            best_option = option
            continue
        best_pixels = int(best_option.get("width", 0)) * int(best_option.get("height", 0))
        pixels = int(option.get("width", 0)) * int(option.get("height", 0))
        if pixels > best_pixels:
            best_option = option

    if best_option is not None:
        return best_option["hlsUrl"], str(best_option.get("label", "best"))

    if isinstance(metadata.get("url"), str):
        return metadata["url"], "default"

    raise RuntimeError(f"No playable HLS URL found for video {metadata.get('id')}.")


def make_output_path(output_dir: Path, entry: dict[str, str], metadata: dict[str, Any], quality_label: str) -> Path:
    lesson_name = entry["lesson_name"] or str(metadata.get("name") or entry["video_id"])
    safe_name = sanitize_filename(lesson_name)
    return output_dir / f"{safe_name} [{entry['video_id']}] {quality_label}.mp4"


def download_spotlight_videos(
    spotlight_id: str,
    token: str,
    output_dir: Path,
    preferred_quality: str,
    list_only: bool,
) -> list[dict[str, str]]:
    spotlight = fetch_spotlight(spotlight_id, token)
    entries = collect_video_entries(spotlight)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, str]] = []
    for index, entry in enumerate(entries, start=1):
        metadata = fetch_video_metadata(entry["video_id"], token)
        playlist_url, quality_label = choose_quality_url(metadata, preferred_quality)
        output_path = make_output_path(output_dir, entry, metadata, quality_label)

        result = {
            "index": str(index),
            "video_id": entry["video_id"],
            "lesson_name": entry["lesson_name"] or str(metadata.get("name", "")),
            "quality": quality_label,
            "playlist_url": playlist_url,
            "output_path": str(output_path),
        }
        results.append(result)
        print(json.dumps(result, ensure_ascii=True))

        if list_only:
            continue
        if output_path.exists():
            print(f"Skipping existing file: {output_path}")
            continue

        download_to_path(playlist_url, output_path)

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download all Voomly videos from a spotlight.")
    parser.add_argument("spotlight_id", help="Spotlight id, for example 7qfgdp2pny")
    parser.add_argument("--token", help="Voomly bearer token")
    parser.add_argument("--output-dir", default="spotlight_downloads", help="Output directory")
    parser.add_argument("--quality", default="1080p", help="Preferred quality label")
    parser.add_argument("--list-only", action="store_true", help="Only print resolved video outputs")
    return parser


def main() -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()
    token = args.token or os.environ.get("VOOMLY_TOKEN")
    if not token:
        parser.error("Missing token. Set VOOMLY_TOKEN in .env or pass --token.")

    download_spotlight_videos(
        spotlight_id=args.spotlight_id,
        token=token,
        output_dir=Path(args.output_dir),
        preferred_quality=args.quality,
        list_only=args.list_only,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
