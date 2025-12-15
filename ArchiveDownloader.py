import curses
import urllib.request
import urllib.parse
import json
import os
import sys
import struct
import threading
import ssl
import time
import re
import unicodedata
from html.parser import HTMLParser

# --- PROJECT SETTINGS ---
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(PROJECT_DIR, "app.log")
CONFIG_FILE = os.path.join(PROJECT_DIR, "controls.json")
KEYS_FILE = os.path.join(PROJECT_DIR, "keys.txt")
COLLECTIONS_FILE = os.path.join(PROJECT_DIR, "collections.json")
CACHE_DIR = os.path.join(PROJECT_DIR, "cache")

if not os.path.exists(CACHE_DIR): os.makedirs(CACHE_DIR)

# --- STORAGE CONFIGURATION ---
# Note: On R36S/ArkOS, the main storage mount point is named "/roms".
# We keep this string to ensure compatibility with the device's file system.
STORAGE_ROOT = "/roms"
if not os.path.exists(STORAGE_ROOT): STORAGE_ROOT = "."

# --- HEADERS ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
try:
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE, "r") as f:
            lines = f.read().splitlines()
            if len(lines) >= 2:
                HEADERS["Authorization"] = f"LOW {lines[0].strip()}:{lines[1].strip()}"
except: pass

# --- GLOBAL COLLECTIONS LIST ---
COLLECTIONS = []

# --- UTILS ---
class LinkParser(HTMLParser):
    def __init__(self, target_ext):
        super().__init__()
        self.links = []
        self.target_ext = target_ext.lower()
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for attr in attrs:
                if attr[0] == 'href':
                    raw = attr[1]
                    if raw.startswith('//'): raw = 'https:' + raw
                    if 'sort=' in raw: continue
                    decoded = urllib.parse.unquote(raw)
                    lower = decoded.lower()
                    if lower.endswith(self.target_ext) or lower.endswith('.zip') or lower.endswith('.7z'):
                        self.links.append({'name': raw, 'size': None})

def safe_str(text):
    try:
        text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
        text = re.sub(r'[^a-zA-Z0-9 \-\.\_\(\)\[\]]', '', text)
    except: text = "?"
    return text

def format_size(size_bytes):
    if not size_bytes: return "0B"
    try:
        s = float(size_bytes)
        if s > 1024*1024*1024: return f"{s/(1024*1024*1024):.1f}GB"
        if s > 1024*1024: return f"{s/(1024*1024):.1f}MB"
        if s > 1024: return f"{s/1024:.0f}KB"
        return f"{int(s)}B"
    except: return "0B"

def get_cache_path(sys_name):
    safe = re.sub(r'[^a-zA-Z0-9]', '_', sys_name)
    return os.path.join(CACHE_DIR, f"{safe}.json")

def log(msg):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except: pass

def safe_addstr(win, y, x, text, color_pair_id):
    try:
        h, w = win.getmaxyx()
        if y >= h or x >= w: return
        max_len = w - x - 1
        if len(text) > max_len: text = text[:max_len]
        win.attron(curses.color_pair(color_pair_id))
        win.addstr(y, x, text)
        win.attroff(curses.color_pair(color_pair_id))
    except curses.error: pass

# --- LOADER ---
def load_collections(stdscr):
    global COLLECTIONS
    if os.path.exists(COLLECTIONS_FILE):
        try:
            with open(COLLECTIONS_FILE, "r") as f:
                data = json.load(f)
                COLLECTIONS = []
                for s in data:
                    COLLECTIONS.append((
                        s.get('name', 'Unknown'),
                        s.get('method', 'HTML'),
                        s.get('url', ''),
                        s.get('filter', ''),
                        s.get('folder', 'roms'),
                        s.get('extension', '.zip')
                    ))
                if not COLLECTIONS: raise ValueError("Empty List")
                return True
        except: pass
    
    h, w = stdscr.getmaxyx()
    stdscr.clear()
    box_h, box_w = 10, 48
    by, bx = (h - box_h)//2, (w - box_w)//2
    
    for y in range(by, by+box_h): safe_addstr(stdscr, y, bx, " " * box_w, 3)
    safe_addstr(stdscr, by, bx, "+" + "-"*(box_w-2) + "+", 3)
    safe_addstr(stdscr, by+box_h-1, bx, "+" + "-"*(box_w-2) + "+", 3)
    for y in range(by+1, by+box_h-1):
        safe_addstr(stdscr, y, bx, "|", 3)
        safe_addstr(stdscr, y, bx+box_w-1, "|", 3)
        
    safe_addstr(stdscr, by+2, bx+2, "ERROR: CONFIG NOT FOUND", 3)
    safe_addstr(stdscr, by+4, bx+2, "collections.json is missing.", 3)
    safe_addstr(stdscr, by+5, bx+2, "Please check your tools folder.", 3)
    safe_addstr(stdscr, by+7, bx+2, "PRESS ANY KEY TO EXIT", 3)
    
    stdscr.refresh()
    stdscr.nodelay(False)
    stdscr.getch()
    return False

# --- INPUT DRIVER ---
input_state = { 
    'A': False, 'B': False, 'X': False, 'Y': False, 'START': False, 
    'UP': False, 'DOWN': False, 'LEFT': False, 'RIGHT': False 
}
BTN_MAP = {} 

def load_controls():
    global BTN_MAP
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                BTN_MAP = {int(k): v for k, v in data.items()}
                return True
        except: pass
    return False

def save_controls():
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(BTN_MAP, f)
    except: pass

def input_worker():
    try: js_dev = open("/dev/input/js0", "rb")
    except: return
    while True:
        ev = js_dev.read(8)
        if ev:
            _, v, t, n = struct.unpack('IhBB', ev)
            if t == 1:
                is_pressed = (v == 1)
                if n in BTN_MAP: input_state[BTN_MAP[n]] = is_pressed
            elif t == 2:
                if n == 1: input_state['UP'], input_state['DOWN'] = (v < -20000), (v > 20000)
                elif n == 0: input_state['LEFT'], input_state['RIGHT'] = (v < -20000), (v > 20000)

# --- KEYBOARD ---
KEYBOARD_LAYOUT = [
    ['1','2','3','4','5','6','7','8','9','0'],
    ['Q','W','E','R','T','Y','U','I','O','P'],
    ['A','S','D','F','G','H','J','K','L'],
    ['Z','X','C','V','B','N','M','.','-'],
    ['SPACE', 'BACK', 'DONE']
]

def run_keyboard(stdscr, title):
    search_term = ""
    ky, kx = 1, 0
    last_input = 0
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        box_h, box_w = 14, 50
        by, bx = (h - box_h)//2, (w - box_w)//2
        for y in range(by, by+box_h): safe_addstr(stdscr, y, bx, " " * box_w, 1)
        safe_addstr(stdscr, by, bx, "+" + "-"*(box_w-2) + "+", 3)
        safe_addstr(stdscr, by+box_h-1, bx, "+" + "-"*(box_w-2) + "+", 3)
        for y in range(by+1, by+box_h-1):
            safe_addstr(stdscr, y, bx, "|", 3)
            safe_addstr(stdscr, y, bx+box_w-1, "|", 3)
        safe_addstr(stdscr, by+1, bx+2, title.center(box_w-4), 3)
        safe_addstr(stdscr, by+3, bx+2, f"[{search_term}]".center(box_w-4), 3)
        
        start_y = by + 5
        for r, row in enumerate(KEYBOARD_LAYOUT):
            row_str_len = len(row) * 3
            start_x = bx + (box_w - row_str_len) // 2
            for c, key_char in enumerate(row):
                color = 2 if (r == ky and c == kx) else 1
                width = 6 if len(key_char) > 1 else 3
                pos_x = start_x + (c*width) - (c*(width-3))
                safe_addstr(stdscr, start_y + r, pos_x, f" {key_char} ", color)
        
        safe_addstr(stdscr, h-1, 0, " A:TYPE  B:DEL  START:CONFIRM ".center(w), 2)
        stdscr.refresh()
        
        now = time.time()
        if now - last_input > 0.15:
            if input_state['UP']: 
                ky = max(0, ky - 1)
                kx = min(kx, len(KEYBOARD_LAYOUT[ky])-1)
                last_input = now
            elif input_state['DOWN']:
                ky = min(len(KEYBOARD_LAYOUT)-1, ky + 1)
                kx = min(kx, len(KEYBOARD_LAYOUT[ky])-1)
                last_input = now
            elif input_state['LEFT']:
                kx = max(0, kx - 1)
                last_input = now
            elif input_state['RIGHT']:
                kx = min(len(KEYBOARD_LAYOUT[ky])-1, kx + 1)
                last_input = now
            elif input_state['A']:
                key = KEYBOARD_LAYOUT[ky][kx]
                if key == 'SPACE': search_term += " "
                elif key == 'BACK': search_term = search_term[:-1]
                elif key == 'DONE': return search_term
                else: search_term += key
                last_input = now + 0.1
            elif input_state['B']:
                search_term = search_term[:-1]
                last_input = now + 0.1
            elif input_state['START']: return search_term
        curses.napms(30)

# --- NETWORK ---
try: ssl._create_default_https_context = ssl._create_unverified_context
except: pass

def fetch_html_list(sys_name, url, ext, force_refresh=False):
    cache_file = get_cache_path(sys_name)
    if not force_refresh and os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f: return json.load(f), None
        except: pass
    
    log(f"Scraping: {url}")
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            parser = LinkParser(ext)
            parser.feed(r.read().decode('utf-8', errors='ignore'))
            files = parser.links
            files.sort(key=lambda x: x['name'])
            with open(cache_file, "w") as f: json.dump(files, f)
            return files, None
    except Exception as e: return None, "Scrape Failed"

def fetch_api_list(sys_name, ident, folder_filter, ext, force_refresh=False):
    cache_file = get_cache_path(sys_name)
    if not force_refresh and os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f: return json.load(f), None
        except: pass
        
    url = f"https://archive.org/metadata/{ident}"
    log(f"API: {url}")
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
            if 'files' not in data: return None, "Empty Lib"
            files = []
            for f in data['files']:
                fname = f['name']
                if folder_filter and folder_filter not in fname: continue
                lname = fname.lower()
                is_match = False
                
                # EXTENSION CHECK
                if ext == ".pbp":
                    if lname.endswith('.pbp') or lname.endswith('.iso') or lname.endswith('.cso') or lname.endswith('.chd') or lname.endswith('.bin') or lname.endswith('.zip'): is_match = True
                elif ext == ".iso":
                    if lname.endswith('.iso') or lname.endswith('.cso') or lname.endswith('.zip'): is_match = True
                else:
                    if lname.endswith(ext) or lname.endswith('.zip') or lname.endswith('.7z'): is_match = True
                
                if is_match:
                    files.append({'name': fname, 'size': f.get('size', 0)})
            files.sort(key=lambda x: x['name'])
            with open(cache_file, "w") as f: json.dump(files, f)
            return files, None
    except Exception as e: return None, "API Failed"

def download_file(stdscr, base_url, filename, folder, file_size_total):
    clean_name = os.path.basename(urllib.parse.unquote(filename))
    dest = os.path.join(STORAGE_ROOT, folder, clean_name)
    if not os.path.exists(os.path.dirname(dest)): 
        try: os.makedirs(os.path.dirname(dest))
        except: return False, "Write Error"
    
    if filename.startswith("http"): url = filename
    else:
        safe_file = filename.replace(" ", "%20")
        url = f"https://archive.org/download/{base_url}/{safe_file}"

    req = urllib.request.Request(url, headers=HEADERS)
    h, w = stdscr.getmaxyx()
    box_y, box_x = h//2 - 5, w//2 - 25
    
    for y in range(box_y, box_y+8): safe_addstr(stdscr, y, box_x, " " * 50, 1)
    safe_addstr(stdscr, box_y, box_x, "+" + "-"*48 + "+", 3)
    safe_addstr(stdscr, box_y+7, box_x, "+" + "-"*48 + "+", 3)
    for y in range(box_y+1, box_y+7):
        safe_addstr(stdscr, y, box_x, "|", 3)
        safe_addstr(stdscr, y, box_x+49, "|", 3)
    
    safe_addstr(stdscr, box_y+1, box_x+2, "DOWNLOADING...", 3)
    safe_addstr(stdscr, box_y+2, box_x+2, safe_str(clean_name)[:46], 1)
    
    start_time = time.time()
    total_size = float(file_size_total) if file_size_total else 0
    
    try:
        with urllib.request.urlopen(req) as r, open(dest, 'wb') as f:
            if total_size == 0:
                 hdr_size = r.getheader('Content-Length')
                 if hdr_size: total_size = float(hdr_size)
            downloaded = 0
            blk = 8192
            while True:
                 if input_state['B']: return False, "CANCELLED"
                 chunk = r.read(blk)
                 if not chunk: break
                 f.write(chunk)
                 downloaded += len(chunk)
                 
                 cur_time = time.time()
                 elapsed = cur_time - start_time
                 speed = downloaded / elapsed if elapsed > 0 else 0
                 
                 if total_size > 0:
                     pct = min(1.0, downloaded / total_size)
                     filled = int(46 * pct)
                     safe_addstr(stdscr, box_y+4, box_x+2, "#" * filled, 2)
                     stat_str = f"{int(pct*100)}% | {format_size(speed)}/s"
                     safe_addstr(stdscr, box_y+5, box_x+2, stat_str.center(46), 1)
                 else:
                     safe_addstr(stdscr, box_y+5, box_x+2, f"{format_size(downloaded)} | {format_size(speed)}/s", 1)
                 stdscr.refresh()
        if input_state['B']: 
             os.remove(dest)
             return False, "CANCELLED"
        return True, "Saved!"
    except Exception as e:
        if os.path.exists(dest): os.remove(dest)
        return False, "DL Error"

# --- UI HELPERS ---
def calibrate(stdscr):
    if load_controls(): return
    h, w = stdscr.getmaxyx()
    steps = [("Hold 'A'", 'A'), ("Hold 'B'", 'B'), ("Hold 'X' (Search)", 'X'), ("Hold 'Y' (Refresh)", 'Y'), ("Hold 'START'", 'START')]
    temp_map = {}
    f = open("/dev/input/js0", "rb")
    for prompt, key in steps:
        stdscr.clear()
        safe_addstr(stdscr, h//2-2, 2, "CALIBRATION", 1)
        safe_addstr(stdscr, h//2, 2, prompt, 1)
        stdscr.refresh()
        btn = None
        while btn is None:
            ev = f.read(8)
            if ev:
                _, v, t, n = struct.unpack('IhBB', ev)
                if t == 1 and v == 1 and n not in temp_map: btn = n
        temp_map[btn] = key
        time.sleep(0.4)
    f.close()
    global BTN_MAP
    BTN_MAP = temp_map
    save_controls()

def get_letter_jump(current_idx, items, direction):
    if not items: return 0
    current_char = safe_str(items[current_idx]['name'])[0].upper()
    if direction == 1:
        for i in range(current_idx + 1, len(items)):
            if safe_str(items[i]['name'])[0].upper() != current_char: return i
        return 0
    else:
        for i in range(current_idx, -1, -1):
            char = safe_str(items[i]['name'])[0].upper()
            if char != current_char:
                prev_char = char
                for j in range(i, -1, -1):
                     if safe_str(items[j]['name'])[0].upper() != prev_char: return j + 1
                return 0
        return len(items) - 1

def show_popup(stdscr, title, msg, color_pair):
    h, w = stdscr.getmaxyx()
    box_w, box_h = min(50, w-4), 8
    bx, by = (w - box_w) // 2, (h - box_h) // 2
    for y in range(by, by+box_h): safe_addstr(stdscr, y, bx, " " * box_w, color_pair)
    safe_addstr(stdscr, by, bx, "+" + "-"*(box_w-2) + "+", color_pair)
    safe_addstr(stdscr, by+box_h-1, bx, "+" + "-"*(box_w-2) + "+", color_pair)
    for y in range(by+1, by+box_h-1):
        safe_addstr(stdscr, y, bx, "|", color_pair)
        safe_addstr(stdscr, y, bx+box_w-1, "|", color_pair)
    safe_addstr(stdscr, by+1, bx+2, safe_str(title)[:box_w-4].center(box_w-4), color_pair)
    safe_addstr(stdscr, by+3, bx+2, safe_str(msg)[:box_w-4].center(box_w-4), color_pair)
    safe_addstr(stdscr, by+6, bx+2, "PRESS B TO CLOSE".center(box_w-4), color_pair)
    stdscr.refresh()
    while True:
        if input_state['B']: 
            time.sleep(0.3)
            break
        curses.napms(50)

def main(stdscr):
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_GREEN)
    curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.curs_set(0)
    stdscr.nodelay(True)
    
    with open(LOG_FILE, "w") as f: f.write("Session Start\n")
    
    if not load_collections(stdscr): return

    calibrate(stdscr)
    threading.Thread(target=input_worker, daemon=True).start()
    
    view = "COLLECTIONS"
    sel_sys = 0
    sel_game = 0
    full_game_list = []
    game_list = []
    last_input = 0
    
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        stdscr.bkgd(' ', curses.color_pair(1))
        
        # HEADER
        title = "COLLECTIONS" if view == "COLLECTIONS" else COLLECTIONS[sel_sys][0]
        hint = f"[{len(game_list)}] X:Search B:Back" if view == "FILES" else "A:Select Y:Refresh"
        header_txt = f" ARCHIVE BROWSER | {safe_str(title)} | {hint} ".ljust(w)
        
        safe_addstr(stdscr, 0, 0, header_txt, 3)
        safe_addstr(stdscr, 1, 0, "-"*w, 3)
        
        items = [{'name': x[0], 'size': None} for x in COLLECTIONS] if view == "COLLECTIONS" else game_list
        idx = sel_sys if view == "COLLECTIONS" else sel_game
        if idx >= len(items) and items: idx = len(items) - 1
        
        max_rows = h - 4
        start = max(0, idx - (max_rows // 2))
        end = min(len(items), start + max_rows)
        
        for i in range(start, end):
            y = 2 + (i - start)
            raw_name = os.path.basename(urllib.parse.unquote(items[i]['name']))
            display_name = safe_str(raw_name)
            sz_str = format_size(items[i]['size'])
            row_content = f" {display_name}".ljust(w - len(sz_str) - 3) + sz_str + " "
            color = 2 if i == idx else 1
            safe_addstr(stdscr, y, 1, row_content, color)
        
        if view == "COLLECTIONS": footer_txt = " A:SELECT  Y:FORCE REFRESH  START:EXIT "
        else: footer_txt = f" [{len(game_list)}] A:DL  X:SEARCH  L/R:JUMP  B:BACK "
        safe_addstr(stdscr, h-1, 0, footer_txt.center(w), 2)
        
        stdscr.refresh()
        
        now = time.time()
        if now - last_input > 0.1:
            if input_state['UP']:
                if view == "COLLECTIONS": sel_sys = max(0, sel_sys - 1)
                else: sel_game = max(0, sel_game - 1)
                last_input = now
            elif input_state['DOWN']:
                if view == "COLLECTIONS": sel_sys = min(len(items)-1, sel_sys + 1)
                else: sel_game = min(len(items)-1, sel_game + 1)
                last_input = now
            elif input_state['RIGHT']:
                if view == "FILES": sel_game = get_letter_jump(sel_game, game_list, 1)
                last_input = now + 0.2
            elif input_state['LEFT']:
                if view == "FILES": sel_game = get_letter_jump(sel_game, game_list, -1)
                last_input = now + 0.2
            elif input_state['X']:
                if view == "FILES":
                    term = run_keyboard(stdscr, "SEARCH")
                    if term is not None:
                        term = term.lower()
                        if term == "": game_list = full_game_list
                        else: game_list = [g for g in full_game_list if term in urllib.parse.unquote(g['name']).lower()]
                        sel_game = 0
                    last_input = now + 0.3
            elif input_state['B']:
                if view == "FILES": 
                    view = "COLLECTIONS"
                    game_list = []
                    full_game_list = []
                else: break
                last_input = now + 0.3
                
            elif input_state['A']:
                if view == "COLLECTIONS":
                    h, w = stdscr.getmaxyx()
                    safe_addstr(stdscr, h//2, w//2 - 8, " LOADING... ", 3)
                    stdscr.refresh()
                    
                    sys_data = COLLECTIONS[sel_sys]
                    mode = sys_data[1]
                    if mode == "API":
                        files, err = fetch_api_list(sys_data[0], sys_data[2], sys_data[3], sys_data[5], False)
                    else:
                        files, err = fetch_html_list(sys_data[0], sys_data[2], sys_data[5], False)
                    
                    if files:
                        full_game_list = files
                        game_list = files
                        view = "FILES"
                        sel_game = 0
                    else: show_popup(stdscr, "ERROR", err, 2)
                    last_input = now + 0.3
                
                elif view == "FILES":
                    sys_data = COLLECTIONS[sel_sys]
                    mode = sys_data[1]
                    if mode == "API":
                        success, msg = download_file(stdscr, sys_data[2], game_list[sel_game]['name'], sys_data[4], game_list[sel_game]['size'])
                    else:
                        success, msg = download_file(stdscr, None, game_list[sel_game]['name'], sys_data[4], None)
                    
                    if success: show_popup(stdscr, "SUCCESS", msg, 2)
                    else: show_popup(stdscr, "ERROR", msg, 2)
                    last_input = now + 0.5
            
            elif input_state['Y']:
                if view == "COLLECTIONS":
                    h, w = stdscr.getmaxyx()
                    safe_addstr(stdscr, h//2, w//2 - 8, " REFRESHING... ", 3)
                    stdscr.refresh()
                    sys_data = COLLECTIONS[sel_sys]
                    mode = sys_data[1]
                    if mode == "API":
                        files, err = fetch_api_list(sys_data[0], sys_data[2], sys_data[3], sys_data[5], True)
                    else:
                        files, err = fetch_html_list(sys_data[0], sys_data[2], sys_data[5], True)
                    if files:
                        full_game_list = files
                        game_list = files
                        view = "FILES"
                        sel_game = 0
                    else: show_popup(stdscr, "ERROR", err, 2)
                    last_input = now + 0.3
        curses.napms(30)

if __name__ == "__main__":
    try: curses.wrapper(main)
    except Exception as e:
        with open("crash.log", "w") as f: f.write(str(e))