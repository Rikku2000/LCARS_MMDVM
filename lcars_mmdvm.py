import pygame
import sys
import time
from datetime import datetime
import random
import re
import os
import math
import psutil
import socket

os.putenv('SDL_FBDEV', '/dev/fb0')
os.putenv('SDL_NOMOUSE', '1')

WIDTH, HEIGHT = 1024, 600
FPS = 10
SCROLL_SPEED = 1
MMDVMHOST_FILE = "/etc/mmdvmhost"
IDLE_TIMEOUT = 120

pygame.display.init()
pygame.font.init()
pygame.mouse.set_visible(False)
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("Pi-Star LCARS Monitor")

basedir = os.path.dirname(os.path.realpath(__file__))
clock = pygame.time.Clock()
last_heard = []
last_modes = []
segments = [((0,0,0), "CPU"), ((0,0,0), "RAM"), ((0,0,0), "DISK"), ((0,0,0), "IP")]
last_timestamps = []
current_mode = "Idle"
current_info = "N/A"
tx_active = False
scroll_offset = 0
idle_start = time.time()
screensaver_mode = False
schematic_nodes = []
schematic_links = []
font_large = pygame.font.Font(os.path.join(basedir, 'ariblk.ttf'), int(HEIGHT * 0.10))
font_medium = pygame.font.Font(os.path.join(basedir, 'ariblk.ttf'), int(HEIGHT * 0.07))
font_small = pygame.font.Font(os.path.join(basedir, 'arial.ttf'), int(HEIGHT * 0.05))
font_tiny = pygame.font.Font(os.path.join(basedir, 'arial.ttf'), int(HEIGHT * 0.035))

regex_patterns = {
    "DMR": re.compile(
        r"^[MDI]:\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})(?:\.\d+)?\s+"
        r"DMR\s+Slot\s+(\d+),.*?from\s+([A-Z0-9/-]+)\s+to\s+TG\s+(\d+)",
        re.IGNORECASE
    ),
    "D-Star": re.compile(
        r"^[MDI]:\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})(?:\.\d+)?\s+"
        r"D-?Star.*?from\s+([A-Z0-9/-]+).*?(?:via|to)\s+([A-Z0-9/-]+)",
        re.IGNORECASE
    ),
    "YSF": re.compile(
        r"^[MDI]:\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})(?:\.\d+)?\s+"
        r"YSF.*?from\s+([A-Z0-9/-]+).*?to\s+([^,]+)",
        re.IGNORECASE
    ),
    "NXDN": re.compile(
        r"^[MDI]:\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})(?:\.\d+)?\s+"
        r"NXDN.*?from\s+([A-Z0-9/-]+).*?TG\s+(\d+)",
        re.IGNORECASE
    ),
    "P25": re.compile(
        r"^[MDI]:\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})(?:\.\d+)?\s+"
        r"P25.*?from\s+([A-Z0-9/-]+).*?TG\s+(\d+)",
        re.IGNORECASE
    ),
}

lcars_colors = {
    "orange": (255, 153, 102),
    "peach": (255, 204, 153),
    "pink": (255, 153, 178),
    "purple": (204, 153, 255),
    "blue": (153, 204, 255),
    "red": (255, 102, 102),
    "yellow": (255, 204, 102),
    "teal": (102, 204, 204),
    "green": (102, 255, 153),
    "grey": (180, 180, 180)
}

mode_colors = {
    "DMR": lcars_colors["orange"],
    "D-Star": lcars_colors["blue"],
    "YSF": lcars_colors["pink"],
    "NXDN": lcars_colors["red"],
    "P25": lcars_colors["purple"],
}

panel_rects = {
    "DMR":    pygame.Rect(20, 20, 160, 80),
    "D-Star": pygame.Rect(200, 20, 160, 80),
    "YSF":    pygame.Rect(380, 20, 160, 80),
    "NXDN":   pygame.Rect(560, 20, 160, 80),
    "P25":    pygame.Rect(740, 20, 160, 80),
}

def run_splash():
    splash_start = pygame.time.get_ticks()
    messages = [
        "> Initializing Starfleet Subsystems... OK",
        "> Loading MMDVM Protocol Stack... OK",
        "> Activating Communications Array... OK",
        "> LCARS Interface Online."
    ]
    msg_index = -1
    showing = True
    while showing:
        elapsed = (pygame.time.get_ticks() - splash_start) / 1000.0
        screen.fill((0,0,0))

        pulse = (math.sin(elapsed*2)+1)/2
        alpha = 100 + int(155*pulse)
        title1 = font_medium.render("STARFLEET COMPUTER SYSTEM", True, lcars_colors["orange"])
        title2 = font_medium.render("LCARS TERMINAL: PI-STAR MONITOR", True, lcars_colors["blue"])
        surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        surf.blit(title1, ((WIDTH-title1.get_width())//2, HEIGHT//2 - 50))
        surf.blit(title2, ((WIDTH-title2.get_width())//2, HEIGHT//2 + 20))
        surf.set_alpha(alpha)
        screen.blit(surf, (0,0))

        msg_time = int(elapsed // 2)
        if msg_time != msg_index and msg_index < len(messages)-1:
            msg_index += 1
        msg_surface = font_small.render(messages[msg_index], True, lcars_colors["grey"])
        screen.blit(msg_surface, (20, HEIGHT-40))

        pygame.display.flip()
        clock.tick(FPS)

        if elapsed > 10:
            showing = False
        for event in pygame.event.get():
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                showing = False
                break

def format_timestamp(ts_str):
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d.%m.%Y / %H:%M:%S")
    except:
        return ts_str

class LogTail:
    def __init__(self):
        self.file = None
        self.current_path = None
        self._open_today()

    def _today_path(self):
        today = time.strftime('%Y-%m-%d')
        return f"/var/log/pi-star/MMDVM-{today}.log"

    def _open_today(self):
        path = self._today_path()
        try:
            if self.file:
                try:
                    self.file.close()
                except Exception:
                    pass
            self.file = open(path, 'r')
            self.file.seek(0, os.SEEK_END)
            self.current_path = path
        except Exception:
            self.file = None
            self.current_path = None

    def poll_lines(self):
        if self._today_path() != self.current_path:
            self._open_today()
        lines = []
        if not self.file:
            return lines
        while True:
            pos = self.file.tell()
            line = self.file.readline()
            if not line:
                self.file.seek(pos)
                break
            lines.append(line.strip())
        return lines

def parse_frequencies():
    rx, tx = None, None
    try:
        with open(MMDVMHOST_FILE, "r") as f:
            for line in f:
                if line.startswith("RXFrequency"):
                    rx = int(line.split("=")[1].strip()) / 1e6
                elif line.startswith("TXFrequency"):
                    tx = int(line.split("=")[1].strip()) / 1e6
        if rx and tx:
            return f"RX: {rx:.3f} MHz  |  TX: {tx:.3f} MHz"
    except:
        pass
    return "Frequencies not found"

freq_text = parse_frequencies()

def draw_screensaver(frame):
    screen.fill((0,0,0))
    pulse = (math.sin(pygame.time.get_ticks()/1000.0)+1)/2
    alpha = int(100 + 155*pulse)
    text1 = font_medium.render("STARFLEET COMPUTER SYSTEM", True, (255,153,102))
    text2 = font_medium.render("MONITOR STANDBY", True, (153,204,255))
    surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    surf.blit(text1, ((WIDTH-text1.get_width())//2, HEIGHT//2 - 50))
    surf.blit(text2, ((WIDTH-text2.get_width())//2, HEIGHT//2 + 20))
    surf.set_alpha(alpha)
    screen.blit(surf, (0,0))

def draw_block(x, y, w, h, color, label="", font=None, roundness=20, highlight=False, border=True, center_label=False):
    rect = pygame.Rect(x, y, w, h)
    if highlight:
        border_color = (255, 255, 0) if pygame.time.get_ticks() // 400 % 2 == 0 else color
        pygame.draw.rect(screen, border_color, rect, border_radius=roundness)
        pygame.draw.rect(screen, color, rect.inflate(-6,-6), border_radius=roundness)
    else:
        pygame.draw.rect(screen, color, rect, border_radius=roundness)
    if border:
        pygame.draw.rect(screen, (0,0,0), rect, 3, border_radius=roundness)
    if label:
        txt_surface = font.render(label, True, (0, 0, 0))
        if center_label:
            tx = rect.x + (rect.width - txt_surface.get_width()) // 2
            ty = rect.y + (rect.height - txt_surface.get_height()) // 2
            screen.blit(txt_surface, (tx, ty))
        else:
            screen.blit(txt_surface, (x + 10, y + (h - txt_surface.get_height()) // 2))

def draw_text_centered(text, rect, font, color=(255,255,255)):
    surface = font.render(text, True, color)
    tx = rect.x + (rect.width - surface.get_width()) // 2
    ty = rect.y + (rect.height - surface.get_height()) // 2
    screen.blit(surface, (tx, ty))

def init_schematic(x, y, w, h):
    global schematic_nodes, schematic_links
    schematic_nodes = [(x+random.randint(40, w-40), y+random.randint(40, h-40)) for _ in range(6)]
    schematic_links = []
    for i in range(len(schematic_nodes)):
        for j in range(i+1, len(schematic_nodes)):
            if random.random() < 0.4:
                schematic_links.append((i,j))

def draw_schematic(x, y, w, h, frame):
    rect = pygame.Rect(x, y, w, h)
    pygame.draw.rect(screen, (40,40,40), rect, border_radius=30)
    pygame.draw.rect(screen, lcars_colors["orange"], rect, 3, border_radius=30)
    for idx, (nx, ny) in enumerate(schematic_nodes):
        pulse = 6 + int(2 * (1+math.sin(frame/10.0 + idx)))
        color = lcars_colors["blue"] if frame % 30 < 15 else lcars_colors["yellow"]
        pygame.draw.circle(screen, color, (nx, ny), pulse)
        draw_text_centered(str(idx+1), pygame.Rect(nx, ny, 30, 30), font_small, lcars_colors["orange"])
    for (i,j) in schematic_links:
        n1, n2 = schematic_nodes[i], schematic_nodes[j]
        link_color = lcars_colors["pink"] if frame % 20 < 10 else lcars_colors["purple"]
        pygame.draw.line(screen, link_color, n1, n2, 2)

def draw_sweep():
    sweep_x = (pygame.time.get_ticks() // 10) % WIDTH
    sweep_rect = pygame.Rect(sweep_x, 0, 80, HEIGHT)
    s = pygame.Surface((80, HEIGHT), pygame.SRCALPHA)
    s.fill((255, 255, 200, 40))
    screen.blit(s, sweep_rect)

def get_ip_address(remote_server="google.com"):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((remote_server, 80))
        return s.getsockname()[0]

def get_system_info():
    cpu = psutil.cpu_percent(interval=0)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    try:
        ip=get_ip_address()
    except:
        ip = "0.0.0.0"
    return cpu, ram, disk, ip

def usage_color(value):
    if value < 50:
        return lcars_colors["green"]
    elif value < 80:
        return lcars_colors["yellow"]
    else:
        return lcars_colors["red"]

def lcars_dashboard(frame):
    global scroll_offset, segments
    screen.fill((0,0,0))

    draw_block(0, 0, 200, 60, lcars_colors["purple"], " LCARS 105", font_small)
    draw_block(200, 0, 400, 60, lcars_colors["orange"], "PI-STAR MMDVM", font_medium)
    star_date = time.strftime("   DATE %d.%m.%Y %H:%M:%S  ")
    draw_block(600, 0, WIDTH-600, 60, lcars_colors["peach"], star_date, font_small)

    y_top = 75
    modes = ["DMR", "D-Star", "YSF", "NXDN", "P25"]
    x_top = 140
    for m in modes:
        w = 140 if m != "P25" else 120
        highlight = (m == current_mode)
        draw_block(x_top, y_top, w, 40, mode_colors[m], m.upper(), font_small, roundness=15, highlight=highlight, center_label=True)
        x_top += w + 20

    log_rect = pygame.Rect(0, 130, WIDTH-320, HEIGHT-250)
    pygame.draw.rect(screen, (40,40,40), log_rect, border_radius=40)
    pygame.draw.rect(screen, lcars_colors["orange"], log_rect, 3, border_radius=40)
    draw_text_centered("EVENT LOG", pygame.Rect(0, 130, WIDTH-320, 40), font_medium, lcars_colors["orange"])

    scroll_offset += SCROLL_SPEED
    line_height = 30
    if scroll_offset >= line_height:
        scroll_offset = 0
        if last_heard:
            last_heard.append(last_heard.pop(0))
            last_modes.append(last_modes.pop(0))
            last_timestamps.append(last_timestamps.pop(0))

    y_offset = 200 - scroll_offset
    max_entry_width = log_rect.width - 180

    for i, entry in enumerate(last_heard[:10]):
        mode = last_modes[i] if i < len(last_modes) else "Idle"
        timestamp = last_timestamps[i] if i < len(last_timestamps) else ""
        base_color = mode_colors.get(mode, (200,200,200))

        truncated_entry = entry
        while font_small.size(truncated_entry)[0] > max_entry_width:
            truncated_entry = truncated_entry[:-1]
        if truncated_entry != entry:
            truncated_entry = truncated_entry[:-3] + "..."

        color = base_color
        if tx_active and mode == current_mode:
            if (pygame.time.get_ticks() // 400) % 2 == 0:
                color = lcars_colors["yellow"]

        entry_surface = font_tiny.render(f"{timestamp}: " + truncated_entry, True, color)
        screen.blit(entry_surface, (10, y_offset))

        entry_rect = pygame.Rect(150, y_offset, max_entry_width, line_height)
        y_offset += line_height

    panel_y = log_rect.h + 140
    panel_h = 60
    freq_panel = pygame.Rect(log_rect.x, panel_y, (log_rect.width), panel_h)

    pygame.draw.rect(screen, lcars_colors["teal"], freq_panel, border_radius=15)
    pygame.draw.rect(screen, (0,0,0), freq_panel, 2, border_radius=15)
    draw_text_centered("FREQUENCIES", pygame.Rect(freq_panel.x, freq_panel.y + 8, freq_panel.width, 20), font_small, (0,0,0))
    draw_text_centered(freq_text, pygame.Rect(freq_panel.x, freq_panel.y + 32, freq_panel.width, 20), font_small, (0,0,0))

    info_x = WIDTH-300
    info_rect = pygame.Rect(info_x, 130, 280, 100)
    pygame.draw.rect(screen, lcars_colors["blue"], info_rect, border_radius=30)
    pygame.draw.rect(screen, (0,0,0), info_rect, 3, border_radius=30)
    draw_text_centered(f"{current_mode}", pygame.Rect(info_x, 150, 280, 25), font_small, (0,0,0))
    draw_text_centered(f"{current_info}", pygame.Rect(info_x, 180, 280, 25), font_small, (0,0,0))

    tx_rect = pygame.Rect(WIDTH-300, 250, 280, 60)
    if tx_active:
        base_color = lcars_colors["red"]
    else:
        base_color = lcars_colors["teal"]
    pygame.draw.rect(screen, base_color, tx_rect, border_radius=30)
    pygame.draw.rect(screen, (0,0,0), tx_rect, 3, border_radius=30)
    label = "TX" if tx_active else "IDLE"
    txt_surface = font_small.render(label, True, (0,0,0))
    tx = tx_rect.x + (tx_rect.width - txt_surface.get_width()) // 2
    ty = tx_rect.y + (tx_rect.height - txt_surface.get_height()) // 2
    screen.blit(txt_surface, (tx, ty))

    draw_schematic(WIDTH-300, HEIGHT-255, 280, 180, frame)

    bar_h = 40
    if frame % (FPS*3) == 0:
        cpu, ram, disk, ip = get_system_info()
        segments = [
            (usage_color(cpu), f"CPU {cpu:.0f}%"),
            (usage_color(ram), f"RAM {ram:.0f}%"),
            (usage_color(disk), f"DISK {disk:.0f}%"),
            (lcars_colors["blue"], f"IP {ip}")
        ]
    seg_w = WIDTH // len(segments)
    x = 0
    for c, label in segments:
        rect = pygame.Rect(x, HEIGHT-bar_h, seg_w, bar_h)
        pygame.draw.rect(screen, c, rect, border_radius=15)
        pygame.draw.rect(screen, (0,0,0), rect, 2, border_radius=15)
        draw_text_centered(label, rect, font_small, (0,0,0))
        x += seg_w

    draw_sweep()

def handle_input(event):
    global idle_start, screensaver_mode, current_mode
    if event.type in (pygame.KEYDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
        idle_start = time.time()
        screensaver_mode = False

    if event.type == pygame.MOUSEBUTTONDOWN:
        mx, my = event.pos
        for mode, rect in panel_rects.items():
            if rect.collidepoint(mx, my):
                print(f"{mode} panel tapped!")
                current_mode = mode

def main():
    global current_mode, current_info, tx_active, last_heard, last_modes, last_timestamps, idle_start, screensaver_mode
    init_schematic(WIDTH-300, HEIGHT-245, 280, 180)
    tail = LogTail()
    frame = 0

    while True:
        frame += 1
        new_entry = False

        lines = tail.poll_lines()
        for line in lines:
            matched = False
            for mode, regex in regex_patterns.items():
                m = regex.search(line)
                if m:
                    g = m.groups()
                    timestamp = g[0]
                    timestamp_fmt = format_timestamp(timestamp)
                    if mode == "DMR" and len(g) >= 4:
                        _, slot, callsign, tg = g
                        current_mode = "DMR"
                        current_info = f"TG {tg} (S{slot})"
                        entry = f"{callsign} - TG {tg}"
                    elif mode == "D-Star" and len(g) >= 3:
                        _, callsign, reflector = g
                        current_mode = "D-Star"
                        current_info = f"via {reflector}"
                        entry = f"{callsign} - {reflector}"
                    elif mode == "YSF" and len(g) >= 3:
                        _, callsign, room = g
                        current_mode = "YSF"
                        current_info = f"Room {room}"
                        entry = f"{callsign} - {room}"
                    elif mode in ("NXDN", "P25") and len(g) >= 3:
                        _, callsign, tg = g
                        current_mode = mode
                        current_info = f"TG {tg}"
                        entry = f"{callsign} - TG {tg}"
                    else:
                        break
                    tx_active = True
                    if entry not in last_heard:
                        last_heard.insert(0, entry)
                        last_modes.insert(0, current_mode)
                        last_timestamps.insert(0, timestamp_fmt)
                        new_entry = True
                    last_heard = last_heard[:25]
                    last_modes = last_modes[:25]
                    last_timestamps = last_timestamps[:25]
                    matched = True
                    break
            if not matched and "end of voice transmission" in line.lower():
                tx_active = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                pygame.quit()
                sys.exit()
            if event.type in (pygame.KEYDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
                idle_start = time.time()
                screensaver_mode = False
            # handle_input(event)


        if frame % (FPS*10) == 0:
            init_schematic(WIDTH-300, HEIGHT-245, 280, 180)

        if new_entry:
            idle_start = time.time()
            screensaver_mode = False

        if time.time() - idle_start > IDLE_TIMEOUT:
            screensaver_mode = True

        if screensaver_mode:
            draw_screensaver(frame)
        else:
            lcars_dashboard(frame)

        pygame.display.flip()
        clock.tick(FPS)

if __name__ == "__main__":
    run_splash()
    main()
