from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import av
import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PLANS_DIR = ROOT / "plans"
OUTPUTS_DIR = ROOT / "outputs"
SCENES_DIR = OUTPUTS_DIR / "scenes"
PROFILE_DIR = ROOT / ".taaft_chrome_profile"
def detect_chrome_path() -> Path:
    override = os.environ.get("CHROME_PATH")
    if override:
        return Path(override)
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return Path(candidate)
    return Path(candidates[0])


CHROME_PATH = detect_chrome_path()
GEN_URL = "https://theresanaiforthat.com/@taaft/video-generator/?ref=header"
LOGIN_URL = "https://theresanaiforthat.com/login/?redirect_to=%2F%40taaft%2Fvideo-generator%2F"
POLLINATIONS_URL = "https://text.pollinations.ai/openai"
DEFAULT_STYLE = "cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade"
DEFAULT_TIER = "fast"
DEFAULT_ORIENTATION = "landscape"
DEFAULT_SCENE_SECONDS = 8
DEFAULT_TARGET_SCENES = 6
DEFAULT_REF_FRAMES = 6
MAX_SEGMENTS = 20
TERMINAL_FAIL = {"failed", "error", "canceled", "cancelled"}
TERMINAL_OK = {"succeeded", "success", "completed"}


class AgentError(RuntimeError):
    pass


class LoginRequired(AgentError):
    pass


class GenerationError(AgentError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def slugify(text: str, fallback: str = "video") -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return value[:64] or fallback


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    os.replace(temp, path)


def save_plan_state(plan: dict[str, Any]) -> None:
    path = plan.get("_plan_path")
    if not path:
        return
    write_json(Path(path), {key: value for key, value in plan.items() if key != "_plan_path"})


def normalize_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", normalize_text(text))
    return [part.strip() for part in parts if part.strip()]


def build_sessions(scenes: list[dict[str, Any]], size: int = 4) -> list[dict[str, Any]]:
    sessions = []
    for offset in range(0, len(scenes), size):
        group = scenes[offset : offset + size]
        sessions.append(
            {
                "name": f"Session {len(sessions) + 1}",
                "scene_indices": [scene["index"] for scene in group],
                "status": "pending",
            }
        )
    return sessions


def compose_scene_prompt(
    beat: str,
    title: str,
    style: str,
    index: int,
    scene_seconds: int,
    camera: str,
    lighting: str,
    continuity: str,
) -> str:
    return (
        f"Create an {scene_seconds}-second cinematic shot for the short film \"{title}\".\n"
        f"STORY BEAT: {beat}\n"
        f"VISUAL: {beat}\n"
        f"CAMERA: {camera}\n"
        f"LIGHTING: {lighting}\n"
        f"CONTINUITY: {continuity}\n"
        f"STYLE: {style}\n"
        "Photorealistic, highly detailed, coherent motion, natural physics. "
        "No text, no subtitles, no captions, no logos, no watermarks. "
        "Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."
    )


def fallback_plan(
    source: str,
    title: str,
    style: str,
    target_scenes: int,
    scene_seconds: int,
    tier: str,
    orientation: str,
) -> dict[str, Any]:
    sentences = split_sentences(source)
    if not sentences:
        sentences = [source.strip() or title]
    target_scenes = max(1, min(MAX_SEGMENTS, target_scenes))
    if len(sentences) > target_scenes:
        chunk = max(1, (len(sentences) + target_scenes - 1) // target_scenes)
        groups = [" ".join(sentences[i : i + chunk]) for i in range(0, len(sentences), chunk)]
        groups = groups[:target_scenes]
    elif len(sentences) < target_scenes:
        words = source.split()
        per_scene = max(6, (len(words) + target_scenes - 1) // target_scenes)
        groups = [" ".join(words[i : i + per_scene]) for i in range(0, len(words), per_scene)]
        groups = groups[:target_scenes]
        while len(groups) < target_scenes:
            groups.append(groups[-1] if groups else title)
    else:
        groups = sentences

    cameras = [
        "slow dolly-in, 35mm lens, shallow depth of field",
        "smooth lateral tracking shot, 50mm lens",
        "locked-off wide shot with subtle push-in",
        "slow orbit around the subject, 40mm lens",
        "handheld follow shot with gentle movement",
        "crane rise revealing the environment",
    ]
    lighting_moods = [
        "cool moonlight with volumetric haze",
        "warm golden-hour backlight and soft rim light",
        "high-contrast noir lighting with deep shadows",
        "soft overcast daylight with muted colors",
        "neon rim light and practical city glow",
        "candlelit amber glow with rich falloff",
    ]

    scenes = []
    for offset, beat in enumerate(groups):
        index = offset + 1
        camera = cameras[offset % len(cameras)]
        lighting = lighting_moods[0]
        if index == 1:
            continuity = "Establish the subject, environment, and color grade for the entire film."
        else:
            continuity = (
                "Continue seamlessly from the last frame of the previous shot. "
                "Preserve the same subject, wardrobe, props, environment, lighting direction, and color grade."
            )
        prompt = compose_scene_prompt(
            beat,
            title,
            style,
            index,
            scene_seconds,
            camera,
            lighting,
            continuity,
        )
        scenes.append(
            {
                "index": index,
                "duration": scene_seconds,
                "title": f"Scene {index}: {' '.join(beat.split()[:7])}",
                "narration": beat,
                "visual": beat,
                "camera": camera,
                "lighting": lighting,
                "continuity": continuity,
                "prompt": prompt,
                "status": "pending",
                "job_id": None,
                "video_url": None,
                "local_video": None,
                "last_frame": None,
                "error": None,
                "attempts": 0,
            }
        )

    return {
        "version": 1,
        "created_at": now_iso(),
        "title": title,
        "logline": source.strip().split("\n")[0][:300],
        "style": style,
        "tier": tier,
        "orientation": orientation,
        "scene_seconds": scene_seconds,
        "source": source,
        "provider": "fallback",
        "scenes": scenes,
        "sessions": build_sessions(scenes),
        "final_video": None,
    }


def extract_json_object(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object found")
    candidate = value[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        try:
            from json_repair import loads as repair_loads

            repaired = repair_loads(candidate)
            if isinstance(repaired, dict):
                return repaired
        except Exception:
            pass
        raise


def pollinations_chat(messages: list[dict[str, str]], max_tokens: int = 6000) -> str:
    body = {
        "model": "openai",
        "messages": messages,
        "temperature": 0.65,
        "max_tokens": max_tokens,
    }
    response = requests.post(POLLINATIONS_URL, json=body, timeout=240)
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Empty LLM response")
    return content


def llm_plan(
    source: str,
    title: str,
    style: str,
    target_scenes: int,
    scene_seconds: int,
    tier: str,
    orientation: str,
) -> dict[str, Any]:
    target_scenes = max(1, min(MAX_SEGMENTS, target_scenes))
    prompt = (
        "You are a senior cinematic director and screenwriter. "
        "Turn the source material into a complete short-film scene plan. "
        "Return valid JSON only, with no markdown and no commentary.\n\n"
        f"Title: {title}\n"
        f"Style: {style}\n"
        f"Target scene count: exactly {target_scenes}\n"
        f"Each scene duration: exactly {scene_seconds} seconds\n\n"
        "Schema:\n"
        '{"title":"...","logline":"...","style":"...","scenes":['
        '{"title":"...","narration":"...","visual":"...","camera":"...","lighting":"...",'
        '"continuity":"...","prompt":"..."}]}\n\n'
        "Rules:\n"
        "1. Preserve the source story, characters, and important details.\n"
        "2. Each scene must be a distinct, filmable 8-second beat.\n"
        "3. Each prompt must be 70-120 words and describe subject, action, environment, camera movement, lighting, and continuity.\n"
        "4. The prompt must say no text, no subtitles, no captions, no logos, no watermarks.\n"
        "5. For scenes after the first, describe how the action continues from the previous scene's final frame.\n"
        "6. Do not mention reference images, <Image 1>, or the extension UI in the prompt.\n"
        "7. Keep one consistent protagonist, wardrobe, environment, and color grade across all scenes.\n"
        "8. Narration must be concise enough for the scene duration.\n"
        "9. Use only ASCII double quotes for JSON syntax. Never use double quotes inside string values; use single quotes instead.\n\n"
        f"Source material:\n{source}"
    )
    messages = [
        {"role": "system", "content": "You are a precise cinematic planner. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            content = pollinations_chat(messages, max_tokens=6000)
            data = extract_json_object(content)
            scenes = data.get("scenes")
            if not isinstance(scenes, list) or not scenes:
                raise ValueError("LLM returned no scenes")
            normalized = []
            for offset, raw in enumerate(scenes[:target_scenes]):
                if not isinstance(raw, dict):
                    continue
                index = offset + 1
                beat = str(raw.get("narration") or raw.get("visual") or "").strip()
                visual = str(raw.get("visual") or beat).strip()
                camera = str(raw.get("camera") or "slow cinematic dolly-in, 35mm lens").strip()
                lighting = str(raw.get("lighting") or "cinematic natural light").strip()
                continuity = str(raw.get("continuity") or "").strip()
                if not continuity:
                    continuity = (
                        "Establish the protagonist, wardrobe, environment, and color grade."
                        if index == 1
                        else "Continue seamlessly from the previous final frame and preserve all visual continuity."
                    )
                prompt_text = str(raw.get("prompt") or "").strip()
                if not prompt_text:
                    prompt_text = compose_scene_prompt(
                        beat,
                        title,
                        style,
                        index,
                        scene_seconds,
                        camera,
                        lighting,
                        continuity,
                    )
                lower = prompt_text.lower()
                if f"{scene_seconds}-second" not in lower and f"{scene_seconds} second" not in lower:
                    prompt_text = f"Create an {scene_seconds}-second cinematic shot.\n" + prompt_text
                if "no text" not in lower:
                    prompt_text += "\nNo text, no subtitles, no captions, no logos, no watermarks."
                normalized.append(
                    {
                        "index": index,
                        "duration": scene_seconds,
                        "title": str(raw.get("title") or f"Scene {index}").strip(),
                        "narration": beat,
                        "visual": visual,
                        "camera": camera,
                        "lighting": lighting,
                        "continuity": continuity,
                        "prompt": prompt_text,
                        "status": "pending",
                        "job_id": None,
                        "video_url": None,
                        "local_video": None,
                        "last_frame": None,
                        "error": None,
                        "attempts": 0,
                    }
                )
            if not normalized:
                raise ValueError("No valid scenes after normalization")
            return {
                "version": 1,
                "created_at": now_iso(),
                "title": str(data.get("title") or title).strip(),
                "logline": str(data.get("logline") or "").strip(),
                "style": str(data.get("style") or style).strip(),
                "tier": tier,
                "orientation": orientation,
                "scene_seconds": scene_seconds,
                "source": source,
                "provider": "pollinations",
                "scenes": normalized,
                "sessions": build_sessions(normalized),
                "final_video": None,
            }
        except Exception as error:
            last_error = error
            log(f"LLM plan attempt {attempt + 1} failed: {error}")
            time.sleep(2)
    raise AgentError(f"LLM planning failed: {last_error}")


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    if args.script:
        source = Path(args.script).read_text(encoding="utf-8")
    elif args.source:
        source = args.source
    elif args.topic:
        source = args.topic
    else:
        raise AgentError("Provide --script, --source, or --topic")

    source = normalize_text(source)
    title = args.title or (source.split("\n")[0][:80] if source else "Untitled Film")
    style = args.style or DEFAULT_STYLE
    target_scenes = max(1, min(MAX_SEGMENTS, args.scenes))
    scene_seconds = max(1, min(10, args.scene_seconds))
    tier = args.tier
    orientation = args.orientation

    if args.provider == "fallback":
        return fallback_plan(source, title, style, target_scenes, scene_seconds, tier, orientation)
    try:
        return llm_plan(source, title, style, target_scenes, scene_seconds, tier, orientation)
    except Exception as error:
        log(f"Falling back to deterministic planner: {error}")
        return fallback_plan(source, title, style, target_scenes, scene_seconds, tier, orientation)


def redact(text: str) -> str:
    return re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[redacted-email]", text or "")


def probe_video(path: Path) -> dict[str, Any]:
    with av.open(str(path)) as container:
        video = container.streams.video[0]
        audio_streams = list(container.streams.audio)
        duration = None
        if container.duration is not None:
            duration = float(container.duration / av.time_base)
        return {
            "width": int(video.codec_context.width),
            "height": int(video.codec_context.height),
            "fps": float(video.average_rate) if video.average_rate else None,
            "audio": bool(audio_streams),
            "duration": duration,
        }


def extract_last_frame(video_path: Path, image_path: Path) -> Path:
    image_path.parent.mkdir(parents=True, exist_ok=True)
    last_frame = None
    with av.open(str(video_path)) as container:
        for frame in container.decode(video=0):
            last_frame = frame
    if last_frame is None:
        raise AgentError(f"No decodable video frames in {video_path}")
    image = last_frame.to_image()
    image.save(image_path)
    return image_path


def extract_reference_frames(
    video_path: Path,
    ref_dir: Path,
    count: int = DEFAULT_REF_FRAMES,
) -> list[Path]:
    video_path = Path(video_path)
    ref_dir = Path(ref_dir)
    if not video_path.exists():
        raise AgentError(f"Reference video missing: {video_path}")
    ref_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(ref_dir.glob("ref_*.png"))
    if len(existing) >= count:
        return existing[:count]
    for old in existing:
        old.unlink()
    with av.open(str(video_path)) as container:
        total = container.streams.video[0].frames or None
    if not total:
        with av.open(str(video_path)) as container:
            total = sum(1 for _ in container.decode(video=0))
    total = max(1, int(total))
    count = max(1, min(count, total))
    if count == 1:
        targets = [total - 1]
    else:
        targets = sorted({int(i * (total - 1) / (count - 1)) for i in range(count)})
    captured: list[tuple[int, Any]] = []
    with av.open(str(video_path)) as container:
        for position, frame in enumerate(container.decode(video=0)):
            if position in targets:
                captured.append((position, frame.to_image()))
                if position >= targets[-1]:
                    break
    captured.sort(key=lambda item: item[0])
    paths = []
    for number, (_, image) in enumerate(captured, start=1):
        out = ref_dir / f"ref_{number:02d}.png"
        image.save(out)
        paths.append(out)
    return paths


def build_reference_prompt(scene_prompt: str, count: int) -> str:
    if count <= 0:
        return scene_prompt
    labels = ", ".join(f"<Image {n}>" for n in range(1, count + 1))
    return (
        f"Reference images {labels} are frames from the previous part of this same film, in chronological order. "
        "The last image is the exact final frame of the previous part. "
        "Continue the story directly from that final frame. "
        "Replicate the protagonist, wardrobe, props, environment, lighting direction, and color grade "
        "exactly as shown in the reference images.\n\n"
        + scene_prompt
    )


def delete_reference_frames(paths: list[Path]) -> int:
    paths = [Path(p) for p in paths if Path(p).exists()]
    dirs: set[Path] = set()
    for path in paths:
        try:
            path.unlink()
            dirs.add(path.parent)
        except OSError as error:
            log(f"Could not delete reference frame {path}: {error}")
    removed = 0
    for directory in dirs:
        try:
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
                removed += 1
        except OSError:
            pass
    return len(paths)


def find_ffmpeg() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def concat_videos(video_paths: list[Path], output_path: Path) -> Path:
    if not video_paths:
        raise AgentError("No videos to concatenate")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_list = output_path.parent / f"{output_path.stem}_concat.txt"
    lines = []
    for path in video_paths:
        escaped = str(path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ffmpeg = find_ffmpeg()
    copy_command = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c",
        "copy",
        str(output_path),
    ]
    result = subprocess.run(copy_command, capture_output=True, text=True)
    if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
        return output_path
    log("Stream-copy concatenation failed; re-encoding")
    probes = [probe_video(path) for path in video_paths]
    all_audio = all(probe["audio"] for probe in probes)
    reencode_command = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
    ]
    if all_audio:
        reencode_command += ["-c:a", "aac", "-b:a", "192k"]
    else:
        reencode_command += ["-an"]
    reencode_command.append(str(output_path))
    result = subprocess.run(reencode_command, capture_output=True, text=True)
    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
        raise AgentError(f"ffmpeg concatenation failed: {redact(result.stderr[-2000:])}")
    return output_path


class TaaftAgent:
    def __init__(
        self,
        profile_dir: Path = PROFILE_DIR,
        output_dir: Path = OUTPUTS_DIR,
        poll_seconds: int = 30,
        job_timeout: int = 3600,
        headless: bool = False,
    ) -> None:
        self.profile_dir = profile_dir
        self.output_dir = output_dir
        self.poll_seconds = max(5, poll_seconds)
        self.job_timeout = max(60, job_timeout)
        self.headless = headless
        self._pw = None
        self.context = None
        self.page = None
        self.config: dict[str, Any] = {}
        self.max_segments = MAX_SEGMENTS

    def __enter__(self) -> "TaaftAgent":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self.context = self._pw.chromium.launch_persistent_context(
            str(self.profile_dir),
            executable_path=str(CHROME_PATH),
            headless=self.headless,
            viewport={"width": 1440, "height": 1100},
            accept_downloads=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self._goto_generator()
        self._ensure_login()
        self._read_config()

    def close(self) -> None:
        try:
            if self.context is not None:
                self.context.close()
        finally:
            if self._pw is not None:
                self._pw.stop()
        self.context = None
        self.page = None
        self._pw = None

    def _wait_for_generator(self, timeout: int = 180) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.page.locator("#user_input").count() > 0 and "Just a moment" not in self.page.title():
                    return
            except Exception:
                pass
            time.sleep(2)
        raise AgentError("Timed out waiting for the generator page or Cloudflare challenge")

    def _goto_generator(self) -> None:
        self.page.goto(GEN_URL, wait_until="domcontentloaded", timeout=90000)
        self._wait_for_generator()

    def _read_config(self) -> None:
        self.config = self.page.evaluate("window.VIDEOGEN_GENERATOR_CONFIG || {}")
        extend = self.config.get("extend") or {}
        self.max_segments = int(extend.get("maxSegments") or MAX_SEGMENTS)
        log(f"Generator ready; max extendable segments: {self.max_segments}")

    def _api_json(self, path: str) -> dict[str, Any]:
        result = self.page.evaluate(
            """async (path) => {
                const response = await fetch(path, {credentials: 'include', headers: {'X-Requested-With': 'XMLHttpRequest'}});
                return {status: response.status, text: await response.text()};
            }""",
            path,
        )
        status = int(result.get("status") or 0)
        text = result.get("text") or ""
        try:
            data = json.loads(text)
        except Exception:
            data = {"raw": text}
        if status == 401:
            raise LoginRequired("TAAFT session expired; run the login command again")
        if status >= 400:
            raise AgentError(f"API {path} returned {status}: {redact(text[:1000])}")
        return data

    def account(self) -> dict[str, Any]:
        return self._api_json("/api/account/?obj_type=0&obj_id=0")

    def quota(self) -> dict[str, Any]:
        data = self._api_json("/api/video-generation/?resume=1")
        return data.get("quota") or {}

    def active_generation(self) -> dict[str, Any] | None:
        data = self._api_json("/api/video-generation/?resume=1")
        generation = data.get("generation")
        return generation if isinstance(generation, dict) else None

    def _ensure_login(self, interactive: bool = True, wait_seconds: int = 600) -> None:
        try:
            account = self.account()
            if account.get("id") and not self.page.locator("#ctrl_login").is_visible():
                log(f"Session active for account id {account.get('id')}")
                return
        except Exception:
            pass
        if not interactive:
            raise LoginRequired("TAAFT login required")
        log("Login required. Opening the TAAFT login page; complete Google/Facebook sign-in in the browser.")
        self.page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            try:
                account = self.account()
                if account.get("id") and not self.page.locator("#ctrl_login").is_visible():
                    log("Login detected")
                    self._goto_generator()
                    return
            except Exception:
                pass
            time.sleep(3)
        raise LoginRequired("Timed out waiting for TAAFT login")

    def _reset_form(self) -> None:
        self._goto_generator()
        self._read_config()

    def _set_tier(self, tier: str) -> None:
        tier = tier if tier in {"fast", "quality"} else DEFAULT_TIER
        button = self.page.locator(f'.videogen_pill[data-videogen-tier="{tier}"]')
        if button.count() == 0:
            raise AgentError(f"Tier button not found: {tier}")
        button.click()
        classes = button.get_attribute("class") or ""
        if "selected" not in classes:
            raise AgentError(f"Could not select tier: {tier}")

    def _set_orientation(self, orientation: str) -> None:
        orientation = orientation if orientation in {"landscape", "portrait"} else DEFAULT_ORIENTATION
        self.page.locator(f'input[name="videogen_orientation"][value="{orientation}"]').check()

    def _set_enhance(self, enabled: bool, extend: bool = False) -> None:
        selector = ".videogen_extend_enhance" if extend else "#videogen_enhance_prompt"
        locator = self.page.locator(selector)
        if locator.count() == 0:
            return
        if enabled:
            locator.check()
        else:
            locator.uncheck()

    def _parse_generation_response(self, response) -> dict[str, Any]:
        status = int(response.status)
        text = response.text()
        try:
            data = json.loads(text)
        except Exception:
            data = {}
        if status == 401:
            raise LoginRequired("TAAFT session expired; run the login command again")
        if status == 409 and data.get("active_generation_id"):
            active_id = data["active_generation_id"]
            log(f"Another generation is active: {active_id}; polling it")
            return self.wait_for_job(active_id)
        if status < 200 or status >= 300 or not data.get("generation"):
            raise GenerationError(f"Generation submission failed ({status}): {redact(text[:1200])}")
        return data["generation"]

    def _set_reference(self, image_path: Path) -> None:
        self.page.locator("#videogen_image_input").set_input_files(str(image_path))
        deadline = time.time() + 30
        while time.time() < deadline:
            if self.page.locator(".videogen_image_chip").count() > 0:
                return
            time.sleep(0.5)
        raise GenerationError(f"Reference image did not attach: {image_path}")

    def _chip_count(self) -> int:
        return self.page.locator(".videogen_image_chip").count()

    def _attach_references(self, paths: list[Path]) -> int:
        paths = [Path(p) for p in paths if Path(p).exists()]
        if not paths:
            raise GenerationError("No reference frames available to attach")
        target = len(paths)
        input_loc = self.page.locator("#videogen_image_input")
        try:
            input_loc.set_input_files([str(p) for p in paths])
            deadline = time.time() + 45
            while time.time() < deadline:
                if self._chip_count() >= target:
                    log(f"Attached {self._chip_count()} reference images in one batch")
                    return self._chip_count()
                time.sleep(0.5)
            log(f"Batch attach only produced {self._chip_count()}/{target} chips; attaching individually")
        except Exception as error:
            log(f"Batch reference attach failed ({error}); attaching individually")
        for path in paths:
            if self._chip_count() >= target:
                break
            before = self._chip_count()
            try:
                input_loc.set_input_files(str(path))
            except Exception:
                continue
            deadline = time.time() + 25
            while time.time() < deadline:
                current = self._chip_count()
                if current > before or current >= target:
                    break
                time.sleep(0.5)
        attached = self._chip_count()
        if attached == 0:
            raise GenerationError("Reference images did not attach")
        return attached

    def _submit_multi_reference(
        self,
        scene: dict[str, Any],
        tier: str,
        orientation: str,
        enhance: bool,
        ref_paths: list[Path],
    ) -> dict[str, Any]:
        self._reset_form()
        attached = self._attach_references(ref_paths)
        prompt = build_reference_prompt(scene["prompt"], attached)
        self.page.locator("#user_input").fill(prompt)
        self._set_tier(tier)
        self._set_orientation(orientation)
        self._set_enhance(enhance)
        log(
            f"Submitting scene {scene['index']} with {attached} reference image(s) "
            f"from the previous scene"
        )
        with self.page.expect_response(
            lambda response: "/api/video-generation" in response.url and response.request.method == "POST",
            timeout=120000,
        ) as response_info:
            self.page.locator("#generate").click()
        generation = self._parse_generation_response(response_info.value)
        scene["job_id"] = generation.get("id")
        scene["status"] = generation.get("status") or "queued"
        scene["video_url"] = generation.get("video_url")
        scene["prompt_sent"] = prompt
        scene["mode"] = generation.get("mode") or "multi_reference"
        scene["reference_frames"] = [str(Path(p)) for p in ref_paths][:attached]
        scene["references_attached"] = attached
        return generation

    def _submit_initial(self, scene: dict[str, Any], tier: str, orientation: str, enhance: bool) -> dict[str, Any]:
        self._reset_form()
        prompt = scene["prompt"]
        self.page.locator("#user_input").fill(prompt)
        self._set_tier(tier)
        self._set_orientation(orientation)
        self._set_enhance(enhance)
        log(f"Submitting scene {scene['index']} initial generation")
        with self.page.expect_response(
            lambda response: "/api/video-generation" in response.url and response.request.method == "POST",
            timeout=120000,
        ) as response_info:
            self.page.locator("#generate").click()
        generation = self._parse_generation_response(response_info.value)
        scene["job_id"] = generation.get("id")
        scene["status"] = generation.get("status") or "queued"
        scene["video_url"] = generation.get("video_url")
        scene["prompt_sent"] = prompt
        scene["mode"] = generation.get("mode")
        return generation

    def _submit_manual_reference(
        self,
        scene: dict[str, Any],
        tier: str,
        orientation: str,
        enhance: bool,
        frame_path: Path,
    ) -> dict[str, Any]:
        self._reset_form()
        prompt = (
            "Use <Image 1> as the exact first frame of this shot. "
            "Continue seamlessly from that frame. Preserve the subject, environment, lighting direction, and color grade.\n\n"
            + scene["prompt"]
        )
        self.page.locator("#user_input").fill(prompt)
        self._set_reference(frame_path)
        self._set_tier(tier)
        self._set_orientation(orientation)
        self._set_enhance(enhance)
        log(f"Submitting scene {scene['index']} with the previous last frame as a manual reference")
        with self.page.expect_response(
            lambda response: "/api/video-generation" in response.url and response.request.method == "POST",
            timeout=120000,
        ) as response_info:
            self.page.locator("#generate").click()
        generation = self._parse_generation_response(response_info.value)
        scene["job_id"] = generation.get("id")
        scene["status"] = generation.get("status") or "queued"
        scene["video_url"] = generation.get("video_url")
        scene["prompt_sent"] = prompt
        scene["mode"] = generation.get("mode") or "manual_reference"
        return generation

    def _wait_for_extend_button(self, timeout: int = 180) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.page.locator("#videogen_extend_open").is_visible():
                    return
            except Exception:
                pass
            time.sleep(2)
        raise GenerationError("Extend button did not become available")

    def _load_generation(self, job_id: str | None) -> None:
        if not job_id:
            return
        try:
            active = self.active_generation()
            if active and active.get("id") == job_id:
                if self.page.locator("#videogen_extend_open").is_visible():
                    return
        except Exception:
            pass
        log(f"Loading parent generation {job_id} from history")
        self._goto_generator()
        selector = f'button[data-videogen-generation-id="{job_id}"]'
        deadline = time.time() + 60
        item = self.page.locator(selector).first
        while time.time() < deadline and item.count() == 0:
            time.sleep(2)
        if item.count() == 0:
            selector = f'[data-videogen-generation-id="{job_id}"]'
            item = self.page.locator(selector).first
            while time.time() < deadline and item.count() == 0:
                time.sleep(2)
        if item.count() == 0:
            raise GenerationError(f"Could not find parent generation {job_id} in history")
        item.click()
        self._wait_for_extend_button(timeout=120)

    def _submit_extend(
        self,
        scene: dict[str, Any],
        enhance: bool,
        parent_job_id: str | None = None,
        parent_frame: Path | None = None,
        tier: str = DEFAULT_TIER,
        orientation: str = DEFAULT_ORIENTATION,
    ) -> dict[str, Any]:
        try:
            self._load_generation(parent_job_id)
            self._wait_for_extend_button()
            self.page.locator("#videogen_extend_open").click()
            textarea = self.page.locator(".videogen_extend_prompt")
            textarea.wait_for(state="visible", timeout=30000)
            textarea.fill(scene["prompt"])
            self._set_enhance(enhance, extend=True)
            log(f"Submitting scene {scene['index']} as an extension of the previous part")
            with self.page.expect_response(
                lambda response: "/api/video-generation" in response.url and response.request.method == "POST",
                timeout=120000,
            ) as response_info:
                self.page.locator(".videogen_extend_submit").click()
            generation = self._parse_generation_response(response_info.value)
            scene["job_id"] = generation.get("id")
            scene["status"] = generation.get("status") or "queued"
            scene["video_url"] = generation.get("video_url")
            scene["parent_id"] = generation.get("parent_id")
            scene["segment_index"] = generation.get("segment_index")
            scene["prompt_sent"] = scene["prompt"]
            scene["mode"] = generation.get("mode")
            return generation
        except (GenerationError, PlaywrightTimeoutError) as error:
            active = self.active_generation()
            if active and active.get("id"):
                log(f"Extend request may already be active; adopting job {active.get('id')}")
                scene["job_id"] = active.get("id")
                scene["status"] = active.get("status") or "queued"
                scene["prompt_sent"] = scene["prompt"]
                scene["mode"] = active.get("mode")
                return active
            if parent_frame is None or not parent_frame.exists():
                raise
            log(f"Extend flow failed ({error}); using the previous last frame as a manual reference")
            return self._submit_manual_reference(scene, tier, orientation, enhance, parent_frame)

    def wait_for_job(self, job_id: str) -> dict[str, Any]:
        deadline = time.time() + self.job_timeout
        url_deadline = None
        last_status = None
        while time.time() < deadline:
            data = self._api_json(f"/api/video-generation/?id={job_id}")
            generation = data.get("generation")
            if not isinstance(generation, dict):
                raise GenerationError(f"Job {job_id} disappeared")
            status = str(generation.get("status") or "")
            if status != last_status:
                queue = generation.get("queue_position")
                eta = generation.get("eta") or {}
                log(
                    f"Job {job_id}: {status}"
                    + (f", queue {queue}" if queue is not None and queue >= 0 else "")
                    + (f", eta {eta.get('lower_seconds')}s" if eta.get("lower_seconds") else "")
                )
                last_status = status
            if status in TERMINAL_FAIL:
                raise GenerationError(f"Generation failed: {redact(str(generation.get('error')))}")
            if status in TERMINAL_OK or generation.get("terminal"):
                if generation.get("video_url"):
                    return generation
                if url_deadline is None:
                    url_deadline = time.time() + 90
                    log(f"Job {job_id} is terminal but the video URL is not ready; waiting")
                if time.time() < url_deadline:
                    time.sleep(5)
                    continue
                raise GenerationError(f"Generation {job_id} finished without a video URL")
            time.sleep(self.poll_seconds)
        raise GenerationError(f"Timed out waiting for job {job_id}")

    def download_video(self, url: str, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
            "Referer": GEN_URL,
        }
        response = requests.get(url, headers=headers, timeout=180)
        response.raise_for_status()
        path.write_bytes(response.content)
        if path.stat().st_size == 0:
            raise GenerationError(f"Downloaded empty video: {url}")
        return path

    def finalize_scene(self, plan: dict[str, Any], scene: dict[str, Any], generation: dict[str, Any]) -> None:
        slug = slugify(plan.get("title") or "video")
        scene_dir = self.output_dir / "scenes" / slug
        scene_dir.mkdir(parents=True, exist_ok=True)
        index = int(scene["index"])
        video_path = scene_dir / f"scene_{index:03d}.mp4"
        frame_path = scene_dir / f"scene_{index:03d}_last.png"
        url = generation.get("video_url")
        if not url:
            raise GenerationError(f"Scene {index} has no video URL")
        log(f"Downloading scene {index}: {url}")
        self.download_video(url, video_path)
        extract_last_frame(video_path, frame_path)
        probe = probe_video(video_path)
        scene["status"] = "succeeded"
        scene["video_url"] = url
        scene["local_video"] = str(video_path)
        scene["last_frame"] = str(frame_path)
        scene["job_id"] = generation.get("id") or scene.get("job_id")
        scene["segment_index"] = generation.get("segment_index")
        scene["parent_id"] = generation.get("parent_id")
        scene["duration_actual"] = probe.get("duration")
        scene["resolution"] = f"{probe.get('width')}x{probe.get('height')}"
        scene["fps"] = probe.get("fps")
        scene["error"] = None
        log(f"Scene {index} ready: {video_path.name} ({scene['resolution']}, {scene['duration_actual']:.3f}s)")

    def generate_scene(
        self,
        plan: dict[str, Any],
        scene: dict[str, Any],
        tier: str,
        orientation: str,
        enhance: bool,
        mode: str = "reference",
        ref_paths: list[Path] | None = None,
        parent_job_id: str | None = None,
        parent_frame: Path | None = None,
    ) -> None:
        paths = [Path(p) for p in (ref_paths or [])]
        if mode == "reference":
            try:
                generation = self._submit_multi_reference(scene, tier, orientation, enhance, paths)
            except (GenerationError, PlaywrightTimeoutError) as error:
                anchor = next((p for p in reversed(paths) if p.exists()), None)
                if anchor is None:
                    raise
                log(
                    f"Multi-reference submission failed for scene {scene['index']} ({error}); "
                    "falling back to the single final-frame reference"
                )
                generation = self._submit_manual_reference(scene, tier, orientation, enhance, anchor)
        elif mode == "extend":
            generation = self._submit_extend(
                scene,
                enhance,
                parent_job_id=parent_job_id,
                parent_frame=parent_frame,
                tier=tier,
                orientation=orientation,
            )
        else:
            generation = self._submit_initial(scene, tier, orientation, enhance)
        scene["status"] = generation.get("status") or "queued"
        scene["attempts"] = int(scene.get("attempts") or 0) + 1
        save_plan_state(plan)
        generation = self.wait_for_job(str(scene["job_id"]))
        self.finalize_scene(plan, scene, generation)
        save_plan_state(plan)
        if paths:
            deleted = delete_reference_frames(paths)
            scene["reference_frames"] = None
            scene["references_attached"] = None
            save_plan_state(plan)
            log(f"Scene {scene['index']} done; cleaned up {deleted} reference image(s) to save storage")

    def run_plan(
        self,
        plan_path: Path,
        max_scenes: int | None = None,
        from_scene: int = 1,
        concat: bool = True,
        session_pause: int = 0,
        enhance: bool = False,
        mode: str = "reference",
        ref_frames: int = DEFAULT_REF_FRAMES,
    ) -> Path | None:
        plan = read_json(plan_path)
        plan["_plan_path"] = str(plan_path)
        scenes = plan.get("scenes") or []
        if not scenes:
            raise AgentError("Plan has no scenes")
        tier = plan.get("tier") or DEFAULT_TIER
        orientation = plan.get("orientation") or DEFAULT_ORIENTATION
        processed = 0
        for position, scene in enumerate(scenes):
            index = int(scene.get("index") or position + 1)
            if index < from_scene:
                continue
            if max_scenes is not None and processed >= max_scenes:
                break
            local_video = scene.get("local_video")
            if scene.get("status") == "succeeded" and local_video and Path(local_video).exists():
                if not scene.get("last_frame") or not Path(scene["last_frame"]).exists():
                    scene["last_frame"] = str(extract_last_frame(Path(local_video), Path(local_video).with_name(Path(local_video).stem + "_last.png")))
                    save_plan_state(plan)
                log(f"Skipping scene {index}: already complete")
                processed += 1
                continue
            if scene.get("status") in {"queued", "processing", "submitting"} and scene.get("job_id"):
                log(f"Resuming scene {index} job {scene['job_id']}")
                generation = self.wait_for_job(str(scene["job_id"]))
                self.finalize_scene(plan, scene, generation)
                save_plan_state(plan)
                processed += 1
                continue
            generation_mode = "initial" if index == 1 else mode
            if generation_mode != "initial":
                previous = scenes[position - 1] if position > 0 else None
                if previous is None or int(previous.get("index") or 0) != index - 1:
                    raise AgentError(f"Cannot generate scene {index} in {generation_mode} mode; previous scene not found")
                if previous.get("status") != "succeeded":
                    raise AgentError(
                        f"Cannot generate scene {index} in {generation_mode} mode: previous scene is not complete"
                    )
            parent_job_id = None
            parent_frame = None
            ref_paths: list[Path] = []
            if generation_mode == "reference":
                local = scenes[position - 1].get("local_video")
                if not local or not Path(local).exists():
                    raise AgentError(
                        f"Cannot generate scene {index} with reference frames: previous scene has no local video"
                    )
                ref_paths = extract_reference_frames(
                    Path(local),
                    Path(local).parent / "refs",
                    ref_frames,
                )
                log(f"Scene {index}: extracted {len(ref_paths)} reference frames from the previous scene")
            elif generation_mode == "extend":
                previous = scenes[position - 1]
                parent_job_id = previous.get("job_id")
                if previous.get("last_frame") and Path(previous["last_frame"]).exists():
                    parent_frame = Path(previous["last_frame"])
            attempts = int(scene.get("attempts") or 0)
            retries = 1
            while True:
                try:
                    self.generate_scene(
                        plan,
                        scene,
                        tier,
                        orientation,
                        enhance,
                        mode=generation_mode,
                        ref_paths=ref_paths,
                        parent_job_id=parent_job_id,
                        parent_frame=parent_frame,
                    )
                    break
                except Exception as error:
                    scene["status"] = "failed"
                    scene["error"] = redact(str(error))
                    scene["attempts"] = attempts + 1
                    save_plan_state(plan)
                    if attempts < retries:
                        attempts += 1
                        log(f"Scene {index} failed; retrying ({attempts}/{retries}): {error}")
                        time.sleep(5)
                        continue
                    raise
            processed += 1
            if session_pause > 0:
                session_indices = []
                for session in plan.get("sessions") or []:
                    if index in session.get("scene_indices", []):
                        session_indices = session.get("scene_indices", [])
                        break
                if session_indices and index == max(session_indices) and index < len(scenes):
                    log(f"Session pause: {session_pause}s")
                    time.sleep(session_pause)

        completed = [s for s in scenes if s.get("status") == "succeeded" and s.get("local_video")]
        if len(completed) < len(scenes):
            log(f"{len(completed)}/{len(scenes)} scenes complete; not concatenating yet")
            return None
        if not concat:
            log("All scenes complete; concatenation skipped")
            return None
        paths = [Path(s["local_video"]) for s in scenes]
        slug = slugify(plan.get("title") or "video")
        final_path = self.output_dir / f"{slug}_final.mp4"
        log(f"Concatenating {len(paths)} scenes into {final_path}")
        concat_videos(paths, final_path)
        plan["final_video"] = str(final_path)
        plan["completed_at"] = now_iso()
        write_json(plan_path, {k: v for k, v in plan.items() if k != "_plan_path"})
        log(f"Final video ready: {final_path}")
        return final_path


def load_plan(path: Path) -> dict[str, Any]:
    plan = read_json(path)
    plan["_plan_path"] = str(path)
    return plan


def latest_plan() -> Path:
    plans = sorted(PLANS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not plans:
        raise AgentError("No plans found; run the plan command first")
    return plans[0]


def command_login(args: argparse.Namespace) -> int:
    with TaaftAgent(profile_dir=Path(args.profile), headless=False) as agent:
        account = agent.account()
        log(f"Logged in as account id {account.get('id')}")
        quota = agent.quota()
        log(f"Quota: {quota}")
    return 0


def command_plan(args: argparse.Namespace) -> int:
    plan = build_plan(args)
    slug = slugify(plan.get("title") or "video")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = Path(args.out) if args.out else PLANS_DIR / f"{slug}_{timestamp}.json"
    write_json(output, plan)
    log(f"Plan saved: {output}")
    log(f"Title: {plan.get('title')}")
    log(f"Scenes: {len(plan.get('scenes') or [])}; provider: {plan.get('provider')}")
    for scene in plan.get("scenes") or []:
        log(f"  {scene['index']}. {scene.get('title')} ({scene.get('duration')}s)")
    return 0


def command_run(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan) if args.plan else latest_plan()
    log(f"Using plan: {plan_path}")
    with TaaftAgent(
        profile_dir=Path(args.profile),
        output_dir=Path(args.outputs),
        poll_seconds=args.poll,
        job_timeout=args.job_timeout,
        headless=False,
    ) as agent:
        quota = agent.quota()
        log(f"Quota: {quota}")
        agent.run_plan(
            plan_path,
            max_scenes=args.max_scenes,
            from_scene=args.from_scene,
            concat=not args.no_concat,
            session_pause=args.session_pause,
            enhance=args.enhance,
            mode=args.mode,
            ref_frames=args.ref_frames,
        )
    return 0


def command_status(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan) if args.plan else latest_plan()
    plan = read_json(plan_path)
    log(f"Plan: {plan_path}")
    log(f"Title: {plan.get('title')}; tier: {plan.get('tier')}; orientation: {plan.get('orientation')}")
    for scene in plan.get("scenes") or []:
        log(
            f"  {scene.get('index')}. {scene.get('status')} "
            f"job={scene.get('job_id')} local={scene.get('local_video')}"
        )
    log(f"Final: {plan.get('final_video')}")
    return 0


def command_concat(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan) if args.plan else latest_plan()
    plan = read_json(plan_path)
    scenes = plan.get("scenes") or []
    paths = [Path(s["local_video"]) for s in scenes if s.get("local_video") and Path(s["local_video"]).exists()]
    if len(paths) != len(scenes):
        raise AgentError(f"Only {len(paths)}/{len(scenes)} scene videos exist")
    slug = slugify(plan.get("title") or "video")
    output = Path(args.out) if args.out else OUTPUTS_DIR / f"{slug}_final.mp4"
    concat_videos(paths, output)
    plan["final_video"] = str(output)
    plan["completed_at"] = now_iso()
    write_json(plan_path, plan)
    log(f"Final video ready: {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TAAFT autonomous scene-chaining video agent")
    parser.add_argument("--profile", default=str(PROFILE_DIR), help="Persistent Chrome profile directory")
    parser.add_argument("--outputs", default=str(OUTPUTS_DIR), help="Output directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser("login", help="Open the browser and wait for manual TAAFT login")
    login_parser.set_defaults(func=command_login)

    plan_parser = subparsers.add_parser("plan", help="Build a detailed scene plan from a script or topic")
    plan_parser.add_argument("--script", help="Path to a script text file")
    plan_parser.add_argument("--source", help="Script text as a string")
    plan_parser.add_argument("--topic", help="Topic or premise")
    plan_parser.add_argument("--title", help="Film title")
    plan_parser.add_argument("--style", help="Visual style bible")
    plan_parser.add_argument("--scenes", type=int, default=DEFAULT_TARGET_SCENES, help="Target scene count")
    plan_parser.add_argument("--scene-seconds", type=int, default=DEFAULT_SCENE_SECONDS, help="Seconds per scene")
    plan_parser.add_argument("--tier", choices=["fast", "quality"], default=DEFAULT_TIER)
    plan_parser.add_argument("--orientation", choices=["landscape", "portrait"], default=DEFAULT_ORIENTATION)
    plan_parser.add_argument("--provider", choices=["pollinations", "fallback"], default="pollinations")
    plan_parser.add_argument("--out", help="Output plan JSON path")
    plan_parser.set_defaults(func=command_plan)

    run_parser = subparsers.add_parser("run", help="Generate all scenes and concatenate the final video")
    run_parser.add_argument("--plan", help="Plan JSON path; defaults to newest plan")
    run_parser.add_argument("--max-scenes", type=int, help="Process at most this many scenes")
    run_parser.add_argument("--from-scene", type=int, default=1, help="Start from this scene index")
    run_parser.add_argument("--poll", type=int, default=30, help="Job poll interval in seconds")
    run_parser.add_argument("--job-timeout", type=int, default=3600, help="Per-job timeout in seconds")
    run_parser.add_argument("--session-pause", type=int, default=0, help="Pause between sessions in seconds")
    run_parser.add_argument(
        "--mode",
        choices=["reference", "extend", "initial"],
        default="reference",
        help="Scene 2+: attach reference frames from the previous scene (reference), use the site's extend feature (extend), or prompt only (initial)",
    )
    run_parser.add_argument(
        "--ref-frames",
        type=int,
        default=DEFAULT_REF_FRAMES,
        help="How many frames to sample from the previous scene as reference images",
    )
    run_parser.add_argument("--no-concat", action="store_true", help="Do not concatenate after generation")
    run_parser.add_argument("--enhance", action="store_true", help="Enable TAAFT prompt enhancement")
    run_parser.set_defaults(func=command_run)

    status_parser = subparsers.add_parser("status", help="Show plan status")
    status_parser.add_argument("--plan", help="Plan JSON path; defaults to newest plan")
    status_parser.set_defaults(func=command_status)

    concat_parser = subparsers.add_parser("concat", help="Concatenate completed scene videos")
    concat_parser.add_argument("--plan", help="Plan JSON path; defaults to newest plan")
    concat_parser.add_argument("--out", help="Final video path")
    concat_parser.set_defaults(func=command_concat)

    return parser


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        log("Interrupted")
        return 130
    except Exception as error:
        log(f"ERROR: {redact(str(error))}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
