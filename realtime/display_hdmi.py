from __future__ import annotations

"""Fullscreen HDMI display for the Ears realtime transcriber — two tracks.

Two scrolling lines:
  * YOU (Dee):   upper line, white, grey "first guess" -> brightens as it scrolls
  * CLAUDE:      lower line, a different color, scrolls the same way

Words enter at the right and glide left at a steady speed (speeding up if they
back up). White-on-black, straight out HDMI via SDL kmsdrm (no desktop needed).

Feed: tails realtime/logs/words.jsonl. Each record:
  {"words":[[word, conf, t], ...]}                 -> YOU track (default)
  {"role":"claude", "words":[[word, conf, t], ...]} -> CLAUDE track

Tunables via env:
  FONT_SIZE     px (default 240)            SCROLL_SPEED  base glide px/sec (default 350)
  CATCHUP       extra px/sec per px backlog (3.0)         MAX_SPEED   cap px/sec (4000)
  GREY_LEVEL    brightness at entry (105)   WHITE_AT      screen frac fully bright (0.50)
  YOU_Y / CLAUDE_Y   line centers as screen frac (0.38 / 0.62)
  CLAUDE_RGB    claude color "r,g,b" (120,205,255)        WORDS_FEED  feed path
"""

import json
import os
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

FEED = Path(os.environ.get("WORDS_FEED", "/cloud-mirror/Ears/realtime/logs/words.jsonl"))
FONT_SIZE = int(os.environ.get("FONT_SIZE", "240"))
SCROLL_SPEED = float(os.environ.get("SCROLL_SPEED", "350"))
CATCHUP = float(os.environ.get("CATCHUP", "3.0"))
MAX_SPEED = float(os.environ.get("MAX_SPEED", "4000"))
GREY_LEVEL = int(os.environ.get("GREY_LEVEL", "105"))
WHITE_AT = float(os.environ.get("WHITE_AT", "0.50"))
# "up the screen" measured from the bottom: you 2/3 up (upper), claude 1/3 up (lower)
YOU_Y = float(os.environ.get("YOU_Y", "0.333"))     # 2/3 up = 1/3 down from top
CLAUDE_Y = float(os.environ.get("CLAUDE_Y", "0.667"))  # 1/3 up = 2/3 down from top
YOU_RGB = (255, 255, 255)
CLAUDE_RGB = tuple(int(x) for x in os.environ.get("CLAUDE_RGB", "120,205,255").split(","))
SPACE_FRAC = 0.33
BG = (0, 0, 0)


def tail(path: Path):
    """Yield appended lines; tolerate missing file and truncation/rotation."""
    while not path.exists():
        time.sleep(0.2)
        yield None
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        fh.seek(0, os.SEEK_END)
        while True:
            pos = fh.tell()
            line = fh.readline()
            if line:
                if line.endswith("\n"):
                    yield line.rstrip("\n")
                else:
                    fh.seek(pos)
                    yield None
            else:
                if path.exists() and path.stat().st_size < pos:
                    fh.seek(0)
                yield None


class Word:
    __slots__ = ("surf", "w", "world_x")

    def __init__(self, surf, world_x):
        self.surf = surf
        self.w = surf.get_width()
        self.world_x = world_x


class Track:
    """One scrolling line of words."""

    def __init__(self, font, space_w, color, y, W):
        self.font = font
        self.space_w = space_w
        self.color = color
        self.y = y
        self.visible: list[Word] = []
        self.scroll_x = 0.0
        self.line_right = W            # world-x right edge of last word

    def add(self, word: str, W: int) -> None:
        surf = self.font.render(word, True, self.color)
        if self.line_right <= self.scroll_x + W:     # caught up: enter at right edge
            wx = self.scroll_x + W
        else:                                         # piling up: queue after the line
            wx = self.line_right + self.space_w
        self.visible.append(Word(surf, wx))
        self.line_right = wx + surf.get_width()

    def update(self, dt: float, W: int) -> None:
        overflow = max(0.0, self.line_right - (self.scroll_x + W))
        speed = min(MAX_SPEED, SCROLL_SPEED + CATCHUP * overflow)
        self.scroll_x += speed * dt
        self.visible = [w for w in self.visible if (w.world_x - self.scroll_x) + w.w > 0]
        if not self.visible:
            self.line_right = self.scroll_x + W

    def draw(self, screen, W: int, denom: float) -> None:
        for wd in self.visible:
            sx = wd.world_x - self.scroll_x
            if sx < W:
                p = (W - sx) / denom
                p = 0.0 if p < 0 else 1.0 if p > 1 else p
                wd.surf.set_alpha(int(GREY_LEVEL + (255 - GREY_LEVEL) * p))
                screen.blit(wd.surf, (int(sx), self.y))


def main() -> None:
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)
    W, H = screen.get_size()
    font = pygame.font.Font(None, FONT_SIZE)
    space_w = int(FONT_SIZE * SPACE_FRAC)
    ls = font.get_linesize()
    denom = max(1.0, W - W * WHITE_AT)

    you = Track(font, space_w, YOU_RGB, int(H * YOU_Y) - ls // 2, W)
    claude = Track(font, space_w, CLAUDE_RGB, int(H * CLAUDE_Y) - ls // 2, W)

    feed = tail(FEED)
    clock = pygame.time.Clock()
    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                running = False

        for _ in range(500):
            line = next(feed)
            if line is None:
                break
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            track = claude if rec.get("role") == "claude" else you
            for entry in rec.get("words", []):
                track.add(entry[0], W)

        you.update(dt, W)
        claude.update(dt, W)

        screen.fill(BG)
        you.draw(screen, W, denom)
        claude.draw(screen, W, denom)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
