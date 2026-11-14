# Local tools

Tools installed on this machine and wired into the taaft agent. Everything in
these folders (except this README) is gitignored. Copy the `Local tools`
block from `.env.example` into `.env` to switch tools on.

## 1. FFmpeg — video assembly, audio mixing, exporting

- Installed via winget (`Gyan.FFmpeg` 9.0.2, full build).
- Command-line: `ffmpeg`, `ffprobe`, `ffplay` (winget links on PATH; open a
  new shell to pick up the PATH change).
- The agent resolves it through `agent.postproduction.ffmpeg_tools.find_ffmpeg`
  (`FFMPEG_PATH` env var → `imageio_ffmpeg` → PATH).

## 2. Kokoro — English AI narration and voices

- GitHub: https://github.com/hexgrad/kokoro (model: hexgrad/Kokoro-82M, Apache).
- Installed as the `kokoro` pip package (Python 3.11, system interpreter) plus
  `soundfile` and eSpeak NG (`eSpeak-NG.eSpeak-NG` via winget) as G2P fallback.
- Voices: American English `a*`/`am_*` (best: `af_heart`, `af_bella`),
  British English `bf_*`/`bm_*` (e.g. `bf_emma`, `bm_george`).
- Model + voice weights download automatically into the HF cache on first run.
- Test: `tools\kokoro\narration_test.wav` was generated at setup time.
- Agent entry point: `agent.postproduction.narration.synthesize_narration`
  (enable with `KOKORO_ENABLED=1`).

## 3. Soundbox — horror SFX, ambience and music

- GitHub: https://github.com/HamSanders/soundbox (MIT).
- Windows app installed at `%LOCALAPPDATA%\Soundbox\soundbox-desktop.exe`.
- Run the app once, download a model on its Models page (Stable Audio 3.0 SFX
  is the default for effects and ambience), then it serves a local HTTP API on
  `http://127.0.0.1:17494`.
- Agent entry point: `agent.postproduction.soundbox.generate_clip`
  (enable with `SOUNDBOX_ENABLED=1`; `SOUNDBOX_MODEL` selects the model).
- It also ships its own MCP server (24 tools) and docs under
  `%LOCALAPPDATA%\Soundbox\app\docs` (API.md, MCP.md, INSTALL-AGENT.md).

## 4. YouTube MCP Server — publishing, research and analytics

- GitHub: https://github.com/joinhackyard/youtube-channel-mcp (MIT).
- Source clone: `tools/youtube-mcp/` (gitignored). Runs via npx from the npm
  registry, so the clone is optional.
- One-time interactive setup (Google OAuth, channel connection, keychain):

  ```powershell
  npx -y @joinhackyard/youtube-channel-mcp setup
  ```

- MCP client config snippet (printed by `npx -y @joinhackyard/youtube-channel-mcp config`):

  ```json
  {
    "mcpServers": {
      "youtube-channel": {
        "command": "npx",
        "args": ["-y", "@joinhackyard/youtube-channel-mcp@latest"]
      }
    }
  }
  ```

- Requires Node 22.13+ (this machine has Node 24.18). Optional ffmpeg for
  transcription (already installed).
- `YOUTUBE_MCP_ENABLED=1` in `.env` marks the pipeline as publish-capable.

## 5. Subtitle Edit — subtitle generation, correction, sync and styling

- GitHub: https://github.com/SubtitleEdit/subtitleedit (GPL-3.0).
- Installed via winget (`Nikse.SubtitleEdit` 5.4.0) with the .NET 10 desktop
  runtime.
- Executable: `C:\Program Files\Subtitle Edit\SubtitleEdit.exe`
  (configurable via `SUBTITLE_EDIT_PATH`).
- Note: SE 5.x (Avalonia rewrite) has **no headless CLI** — `/convert` opens
  the GUI. Batch conversion, sync, styling and speech-to-text (Whisper) are
  done in the GUI via Tools → Batch convert, Synchronization and Video →
  Speech to text. For automated subtitle conversion in the pipeline, FFmpeg
  is used instead (`ffmpeg -i story.srt story.vtt`).
