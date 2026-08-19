"""Generate the macOS ICNS application icon used by the PyInstaller build."""

from __future__ import annotations

# Standard-library modules handle PNG encoding, geometry, process launching, paths, and typing.
import binascii
import math
import struct
import subprocess
import zlib
from collections.abc import Sequence
from pathlib import Path


# The repository root is resolved from this script so the workflow can run it from any cwd.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# macOS iconsets require these exact point sizes with @2x variants for Retina displays.
ICONSET_SIZES = (
    (16, 1),
    (16, 2),
    (32, 1),
    (32, 2),
    (128, 1),
    (128, 2),
    (256, 1),
    (256, 2),
    (512, 1),
    (512, 2),
)

# The icon output lives under build/ because it is a generated packaging artifact.
OUTPUT_ROOT = PROJECT_ROOT / "build"
ICONSET_DIR = OUTPUT_ROOT / "app-icon.iconset"
ICNS_PATH = OUTPUT_ROOT / "app-icon.icns"

# The rendered artwork uses the same role/team concept as media/app icon/app-icon.svg.
VIEWBOX_SIZE = 24.0


# Returns one PNG chunk with the required CRC trailer.
def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Return a PNG chunk for the provided four-byte chunk type and payload."""

    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", binascii.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


# Writes a raw RGBA byte buffer as a standards-compliant PNG file.
def write_png(path: Path, size: int, pixels: bytearray) -> None:
    """Write one square RGBA PNG image to disk."""

    rows = bytearray()
    stride = size * 4
    # PNG scanlines need a filter byte before each row; filter 0 keeps our raw RGBA bytes unchanged.
    for row in range(size):
        rows.append(0)
        start = row * stride
        rows.extend(pixels[start:start + stride])
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + png_chunk(b"IEND", b"")
    )


# Creates a transparent RGBA canvas for drawing one icon size.
def canvas(size: int) -> bytearray:
    """Return a transparent RGBA pixel buffer for a square image."""

    return bytearray(size * size * 4)


# Overwrites one pixel if it is inside the canvas bounds.
def set_pixel(pixels: bytearray, size: int, x: int, y: int, color: tuple[int, int, int, int]) -> None:
    """Set one RGBA pixel on the canvas when the coordinate is in bounds."""

    # Strokes can extend outside the canvas near edges, so out-of-bounds writes are ignored.
    if x < 0 or y < 0 or x >= size or y >= size:
        return
    offset = (y * size + x) * 4
    pixels[offset:offset + 4] = bytes(color)


# Converts a viewBox unit coordinate into a concrete pixel coordinate.
def unit(value: float, size: int) -> float:
    """Return a pixel coordinate for one value in the 24x24 icon viewBox."""

    return value * size / VIEWBOX_SIZE


# Fills a rounded rectangle by checking each pixel against the nearest rounded corner.
def fill_rounded_rect(
    pixels: bytearray,
    size: int,
    bounds: tuple[float, float, float, float],
    radius: float,
    color: tuple[int, int, int, int],
) -> None:
    """Draw a filled rounded rectangle into the canvas."""

    left, top, right, bottom = [unit(value, size) for value in bounds]
    corner_radius = unit(radius, size)
    min_x, max_x = int(left), int(math.ceil(right))
    min_y, max_y = int(top), int(math.ceil(bottom))
    # Each candidate pixel is checked against a clamped corner center to preserve rounded corners.
    for y in range(min_y, max_y):
        for x in range(min_x, max_x):
            cx = min(max(x + 0.5, left + corner_radius), right - corner_radius)
            cy = min(max(y + 0.5, top + corner_radius), bottom - corner_radius)
            # Pixels inside the nearest corner radius belong to the rounded rectangle fill.
            if math.hypot(x + 0.5 - cx, y + 0.5 - cy) <= corner_radius:
                set_pixel(pixels, size, x, y, color)


# Draws a filled circle used for the front role member's head.
def fill_circle(
    pixels: bytearray,
    size: int,
    center: tuple[float, float],
    radius: float,
    color: tuple[int, int, int, int],
) -> None:
    """Draw a filled circle into the canvas."""

    cx, cy = unit(center[0], size), unit(center[1], size)
    pr = unit(radius, size)
    # Restrict the scan to the circle's bounding box so large icon sizes remain cheap to render.
    for y in range(int(cy - pr), int(math.ceil(cy + pr))):
        for x in range(int(cx - pr), int(math.ceil(cx + pr))):
            # The distance check turns the bounding box into the actual filled circle.
            if math.hypot(x + 0.5 - cx, y + 0.5 - cy) <= pr:
                set_pixel(pixels, size, x, y, color)


# Draws a ring by accepting pixels whose distance falls within the stroke band.
def stroke_circle(
    pixels: bytearray,
    size: int,
    center: tuple[float, float],
    radius: float,
    width: float,
    color: tuple[int, int, int, int],
) -> None:
    """Draw a stroked circle into the canvas."""

    cx, cy = unit(center[0], size), unit(center[1], size)
    pr = unit(radius, size)
    half_width = unit(width, size) / 2
    outer = pr + half_width
    inner = pr - half_width
    # The ring is drawn by scanning only the stroke's outer bounding box.
    for y in range(int(cy - outer), int(math.ceil(cy + outer))):
        for x in range(int(cx - outer), int(math.ceil(cx + outer))):
            distance = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            # Keeping pixels between inner and outer radii produces a hollow circle stroke.
            if inner <= distance <= outer:
                set_pixel(pixels, size, x, y, color)


# Returns the distance from a pixel center to a line segment.
def distance_to_segment(px: float, py: float, start: tuple[float, float], end: tuple[float, float]) -> float:
    """Return the shortest distance from one point to a finite line segment."""

    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    length_squared = dx * dx + dy * dy
    # Degenerate segments behave like a round dot instead of dividing by zero.
    if length_squared == 0:
        return math.hypot(px - sx, py - sy)
    amount = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / length_squared))
    closest_x = sx + amount * dx
    closest_y = sy + amount * dy
    return math.hypot(px - closest_x, py - closest_y)


# Draws a round-capped line segment for the role outlines.
def stroke_line(
    pixels: bytearray,
    size: int,
    start: tuple[float, float],
    end: tuple[float, float],
    width: float,
    color: tuple[int, int, int, int],
) -> None:
    """Draw a stroked line segment into the canvas."""

    start_px = (unit(start[0], size), unit(start[1], size))
    end_px = (unit(end[0], size), unit(end[1], size))
    half_width = unit(width, size) / 2
    left = int(min(start_px[0], end_px[0]) - half_width)
    right = int(math.ceil(max(start_px[0], end_px[0]) + half_width))
    top = int(min(start_px[1], end_px[1]) - half_width)
    bottom = int(math.ceil(max(start_px[1], end_px[1]) + half_width))
    # Only the capsule around the segment is scanned, which keeps wide icon rendering bounded.
    for y in range(top, bottom):
        for x in range(left, right):
            # Pixels within the stroke radius of the finite segment form a round-capped line.
            if distance_to_segment(x + 0.5, y + 0.5, start_px, end_px) <= half_width:
                set_pixel(pixels, size, x, y, color)


# Draws connected line segments without requiring an SVG renderer in CI.
def stroke_polyline(
    pixels: bytearray,
    size: int,
    points: Sequence[tuple[float, float]],
    width: float,
    color: tuple[int, int, int, int],
) -> None:
    """Draw a connected polyline into the canvas."""

    # Consecutive points are rendered as independent round-capped strokes to approximate SVG paths.
    for index in range(len(points) - 1):
        stroke_line(pixels, size, points[index], points[index + 1], width, color)


# Renders the app icon artwork at a requested pixel size.
def render_icon(size: int) -> bytearray:
    """Return RGBA pixels for one GitDesk app icon size."""

    pixels = canvas(size)
    white = (255, 255, 255, 255)
    fill_rounded_rect(pixels, size, (1.0, 1.0, 23.0, 23.0), 5.0, (19, 24, 30, 255))
    stroke_circle(pixels, size, (6.2, 6.8), 2.1, 1.8, white)
    stroke_polyline(pixels, size, ((2.6, 14.2), (4.4, 12.3), (6.2, 11.8), (7.0, 11.8)), 1.8, white)
    stroke_circle(pixels, size, (17.8, 6.8), 2.1, 1.8, white)
    stroke_polyline(pixels, size, ((21.4, 14.2), (19.6, 12.3), (17.8, 11.8), (17.0, 11.8)), 1.8, white)
    fill_circle(pixels, size, (12.0, 10.2), 2.9, white)
    stroke_polyline(
        pixels,
        size,
        ((5.9, 20.8), (5.9, 20.3), (7.2, 16.5), (12.0, 14.2), (16.8, 16.5), (18.1, 20.3), (18.1, 20.8)),
        1.8,
        white,
    )
    return pixels


# Returns the filename macOS iconsets expect for one size and scale.
def iconset_name(points: int, scale: int) -> str:
    """Return the iconset PNG filename for one point size and scale."""

    suffix = "" if scale == 1 else "@2x"
    return f"icon_{points}x{points}{suffix}.png"


# Writes every PNG required by iconutil for a complete app icon.
def write_iconset() -> None:
    """Create the app-icon.iconset directory and populate all required PNG sizes."""

    ICONSET_DIR.mkdir(parents=True, exist_ok=True)
    # Every iconset entry is generated at its actual pixel size so iconutil receives complete assets.
    for points, scale in ICONSET_SIZES:
        pixel_size = points * scale
        write_png(ICONSET_DIR / iconset_name(points, scale), pixel_size, render_icon(pixel_size))


# Runs iconutil to convert the generated iconset into the ICNS file PyInstaller expects.
def build_icns() -> None:
    """Generate build/app-icon.icns from the iconset PNG files."""

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    write_iconset()
    subprocess.run(
        ["iconutil", "-c", "icns", "-o", str(ICNS_PATH), str(ICONSET_DIR)],
        check=True,
    )


# Script entry point used by the macOS GitHub Actions packaging job.
def main() -> None:
    """Generate the macOS app icon asset."""

    build_icns()


if __name__ == "__main__":
    main()
