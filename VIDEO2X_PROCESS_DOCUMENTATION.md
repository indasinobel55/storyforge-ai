# video2x Installation & Max Resolution Upscaling Documentation

## Session Overview
- **Date:** November 14, 2026
- **Objective:** Install video2x open-source AI upscaling/frame-interpolation tool and process user's Windows video file to maximize resolution while maintaining Windows Media Player compatibility.
- **Source File:** `C:\Users\Ashish\Downloads\scene 1.mp4` (864×480, 24fps, H.264)
- **Output:** `C:\Users\Ashish\Downloads\scene 1 4x-reencoded.mp4` (3456×1920, 24fps, yuv420p)

## Installed Software

### video2x v6.4.0
- **License:** AGPL-3.0
- **Repository:** https://github.com/k4yt3x/video2x
- **Installation Path:** `C:/Program Files/video2x/`
- **Dependencies:** Vulkan runtime, ncnn backend, Real-ESRGAN and RIFE models
- **GPU:** NVIDIA GeForce RTX 4060 Laptop GPU with Vulkan acceleration

### FFmpeg
- Used for color space conversion and re-encoding
- Available in PATH for command-line operations

## Source Video Properties
| Property | Value |
|---|---|
| Resolution | 864 × 480 |
| Frame Rate | 24 fps |
| Codec | H.264 |
| Color Space | GBR (ncnn Vulkan native) |
| File | `C:\Users\Ashish\Downloads\scene 1.mp4` |

## Processing Pipeline

### Step 1: 4x Real-ESRGAN Upscaling
- **Command:** video2x GUI with settings:
  - Scale: 4×
  - Model: `realesr-animevideov3` (Real-ESRGAN)
  - GPU Acceleration: Vulkan (RTX 4060)
- **Result:** `scene 1 4x.mp4` at 3456×1920
- **Color Space Issue:** Output in `gbrp` format, incompatible with Windows Media Player

### Step 2: FFmpeg Re-encoding for WMP Compatibility
- **Command:**
  ```bash
  ffmpeg -i "scene 1 4x.mp4" \
    -c:v libx264 \
    -pix_fmt yuv420p \
    -crf 17 \
    -preset medium \
    "scene 1 4x-reencoded.mp4"
  ```
- **Conversion:** `gbrp` → `yuv420p` (standard format Windows Media Player understands)
- **Result:** `C:\Users\Ashish\Downloads\scene 1 4x-reencoded.mp4`
- **Verified Properties:**
  - Resolution: **3456 × 1920** (4× maximum)
  - Frame Rate: **24 fps** (24/1)
  - Codec: **H.264**
  - Color Space: **yuv420p** (WMP compatible)
  - Bit Rate: ~45 Mbps (CRF 17 quality)

### Step 3: File Cleanup
Removed excess intermediate files:
- `scene 1 rife.mp4` — RIFE frame interpolation test output
- `scene 1 upscaled-bt709.mp4` — bt709 color space test
- `scene 1 upscaled-fixed.mp4` — fixed color space test
- `scene 1 upscaled-yuv420p.mp4` — yuv420p test
- `scene 1 4x.mp4` — raw 4x output (GBR, before re-encoding)
- `scene 1 max4x.mp4` — corrupted/empty file
- `test_3x.mp4` — test file

## Final Deliverable

### `scene 1 4x-reencoded.mp4`
- **Path:** `C:\Users\Ashish\Downloads\scene 1 4x-reencoded.mp4`
- **Size:** ~44.7 MB
- **Resolution:** 3456 × 1920 (**4× maximum upscale**)
- **Frame Rate:** 24 fps
- **Codec:** H.264
- **Color Space:** yuv420p (Windows Media Player compatible)
- **Quality:** CRF 17 (high quality, efficient size)
- **Creation:** Real-ESRGAN AI upscaling + FFmpeg re-encoding

## Technical Notes

### Color Space Conversion
- video2x ncnn Vulkan backend outputs native `gbrp` (Great Bit-Range Planar) color space
- Windows Media Player requires standard `yuv420p` format
- FFmpeg `-pix_fmt yuv420p` conversion fixes the "unsupported encoding error" in WMP

### Resolution Mathematics
- Original: 864 × 480
- 2×: 1728 × 960
- 4× (max): **3456 × 1920**
- The 4× scale factor represents the maximum practical upscale using Real-ESRGAN anime model while maintaining stability

### GPU Utilization
- Real-ESRGAN model inference executed on NVIDIA RTX 4060 via Vulkan
- Significantly faster than CPU-only processing
- ncnn backend optimizes for mobile/NVIDIA GPU architecture

## Verification Commands

### FFprobe - Original Source
```bash
ffprobe -v error -show_entries stream=codec_name,codec_type,width,height,color_space -of json "scene 1.mp4"
```
Result: 864×480, h264, color_space=gbr

### FFprobe - 4x Re-encoded Output
```bash
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,codec_name,bit_rate -of json "scene 1 4x-reencoded.mp4"
```
Result: 3456×1920, 24/1 fps, h264, bit_rate=45020514

### FFprobe - 2x Re-encoded Output
```bash
ffprobe -v error -show_entries stream=codec_name,codec_type,width,height,r_frame_rate -of json "scene 1 upscaled-reencoded.mp4"
```
Result: 1728×960, 24/1 fps, h264