import contextlib
import os
import time
START_TIME = time.monotonic()   # for the startup timings in the log


def seconds_since_launch():
    """Seconds since rinkhals-ui.sh started this script, for the startup timings in the log.

    It counts the shell, starting Python and importing, which START_TIME can't:
    the shell leaves the printer's uptime in UI_LAUNCHED_UPTIME. Without it
    (the simulator, a script started by hand) it is the time since this file began.
    """
    try:
        launched = float(os.environ['UI_LAUNCHED_UPTIME'])
        with open('/proc/uptime') as f:
            return float(f.read().split()[0]) - launched
    except (KeyError, ValueError, OSError):
        return time.monotonic() - START_TIME


import sys
import json
import re
import logging

import lvgl as lv
import lvgl_rinkhals as lvr

from common import *
import reader
import app_settings
import home_tools
import liquid_layout
import liquid_ui


cache_items = {}

def cache(getter, key = None):
    key = key or ''
    key = f'line:{sys._getframe().f_back.f_lineno}|{key}'
    item = cache_items.get(key)
    if item is None:
        item = getter()
        cache_items[key] = item
    return item
def ellipsis(text, length):
    if len(text) > length:
        text = text[:int(length / 2)] + '...' + text[-int(length / 2):]
    return text


DEBUG_LOGGING = os.getenv('DEBUG_LOGGING')
DEBUG_LOGGING = not not DEBUG_LOGGING

DEBUG_RENDERING = os.getenv('DEBUG_RENDERING')
DEBUG_RENDERING = not not DEBUG_RENDERING

if DEBUG_LOGGING:
    logging.getLogger().setLevel(logging.DEBUG)

lvr.set_debug_rendering(DEBUG_RENDERING)

if USING_SIMULATOR:
    PrinterInfo.simulate(
        model_code='KS1',
        model='Anycubic Kobra',
        rinkhals_version='20250617_01',
        system_version='1.2.3.4',
    )


# Detect Boomslang root
SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
ASSETS_PATH = os.path.join(SCRIPT_PATH, 'assets')

RINKHALS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_PATH)))

USING_SIMULATOR = lv.helpers.is_windows()
USING_SHELL = True
if USING_SIMULATOR:
    if os.system('sh -c "echo"') != 0:
        USING_SHELL = False
    else:
        RINKHALS_ROOT = RINKHALS_ROOT.replace('\\', '/')
    if os.system('sh -c "ls /mnt/c"') == 0:
        RINKHALS_ROOT = '/mnt/' + RINKHALS_ROOT[0].lower() + RINKHALS_ROOT[2:]

# Detect environment and tools
if USING_SIMULATOR:
    RINKHALS_HOME = f'{RINKHALS_ROOT}/../4-apps/home/rinkhals'
    RINKHALS_VERSION = 'dev'
    KOBRA_MODEL = 'Anycubic Kobra'
    KOBRA_MODEL_CODE = 'K3'
    KOBRA_VERSION = '1.2.3.4'

    def list_apps():
        system_apps = [ f.name for f in os.scandir(f'{RINKHALS_HOME}/apps') if f.is_dir() ]
        user_apps = [ f.name for f in os.scandir(f'{RINKHALS_ROOT}/../../../Rinkhals.apps/apps') if f.is_dir() ] if os.path.exists(f'{RINKHALS_ROOT}/../../../Rinkhals.apps/apps') else []
        additional_apps = [ 'test-1', 'test-2', 'test-3', 'test-4', 'test-5', 'test-6', 'test-7', 'test-8' ]
        return ' '.join(system_apps + user_apps + additional_apps)
    def get_app_root(app):
        if os.path.exists(f'{RINKHALS_HOME}/apps/{app}'): return f'{RINKHALS_HOME}/apps/{app}'
        if os.path.exists(f'{RINKHALS_ROOT}/../../../Rinkhals.apps/apps/{app}'): return f'{RINKHALS_ROOT}/../../../Rinkhals.apps/apps/{app}'
        return ''
    def is_app_enabled(app): return '1' if os.path.exists(f'{RINKHALS_HOME}/apps/{app}/.enabled') else '0'
    def get_app_status(app): return 'started' if is_app_enabled(app) == '1' else 'stopped'
    def get_app_pids(app): return str(os.getpid()) if get_app_status(app) == 'started' else ''
    def enable_app(app): pass
    def disable_app(app): pass
    def start_app(app, timeout): pass
    def stop_app(app): pass
    def get_app_property(app, property): return 'https://github.com/Gubir34/Boomslang' if property == 'link_output' else ''
    def set_app_property(app, property, value): pass
    def set_temporary_app_property(app, property, value): pass
    def remove_app_property(app, property): pass
    def clear_app_properties(app): pass

    def are_apps_enabled(): return { a: is_app_enabled(a) for a in list_apps().split(' ') }
else:
    # K3SysUi starts this UI and was itself started by start.sh after it
    # sourced tools.sh, so the variables are normally inherited. Starting a
    # shell and a second Python interpreter just to print them cost seconds
    # on every open; only do that when something is missing.
    ENVIRONMENT_KEYS = ('RINKHALS_ROOT', 'RINKHALS_HOME', 'RINKHALS_VERSION', 'KOBRA_MODEL_ID',
                        'KOBRA_MODEL', 'KOBRA_MODEL_CODE', 'KOBRA_VERSION', 'KOBRA_DEVICE_ID')
    environment = dict(os.environ)
    if not all(environment.get(key) for key in ENVIRONMENT_KEYS if key != 'KOBRA_DEVICE_ID'):
        output = shell('. /useremain/rinkhals/.current/tools.sh && env')
        for line in output.splitlines():
            key, _, value = line.partition('=')
            if key in ENVIRONMENT_KEYS:
                environment[key] = value
    environment.setdefault('KOBRA_DEVICE_ID', '')

    RINKHALS_ROOT = environment['RINKHALS_ROOT']
    RINKHALS_HOME = environment['RINKHALS_HOME']
    RINKHALS_VERSION = environment['RINKHALS_VERSION']
    KOBRA_MODEL_ID = environment['KOBRA_MODEL_ID']
    KOBRA_MODEL = environment['KOBRA_MODEL']
    KOBRA_MODEL_CODE = environment['KOBRA_MODEL_CODE']
    KOBRA_VERSION = environment['KOBRA_VERSION']
    KOBRA_DEVICE_ID = environment['KOBRA_DEVICE_ID']

    def load_tool_function(function_name):
        def tool_function(*args):
            return shell(f'. /useremain/rinkhals/.current/tools.sh && {function_name} ' + ' '.join([ str(a) for a in args ]))
        return tool_function

    # Read-only helpers run in Python (see app_tools.py), the rest in tools.sh
    from app_tools import AppTools
    app_tools = AppTools(RINKHALS_ROOT, RINKHALS_HOME,
                         shell_fallback=lambda function, *args: load_tool_function(function)(*args))

    list_apps = app_tools.list_apps
    get_app_root = app_tools.get_app_root
    get_app_status = load_tool_function('get_app_status')
    get_app_pids = load_tool_function('get_app_pids')
    is_app_enabled = app_tools.is_app_enabled
    enable_app = load_tool_function('enable_app')
    disable_app = load_tool_function('disable_app')
    start_app = load_tool_function('start_app')
    stop_app = load_tool_function('stop_app')
    get_app_property = app_tools.get_app_property
    set_app_property = load_tool_function('set_app_property')
    set_temporary_app_property = load_tool_function('set_temporary_app_property')
    remove_app_property = load_tool_function('remove_app_property')
    clear_app_properties = load_tool_function('clear_app_properties')

    are_apps_enabled = app_tools.are_apps_enabled
        
# Detect LAN mode
REMOTE_MODE = 'cloud'
if os.path.isfile('/useremain/dev/remote_ctrl_mode'):
    with open('/useremain/dev/remote_ctrl_mode', 'r') as f:
        REMOTE_MODE = f.read().strip()


def printer_ip():
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(('10.255.255.255', 1))
        ip = sock.getsockname()[0]
        return None if ip.startswith('127.') or ip == '0.0.0.0' else ip
    except Exception:
        return None
    finally:
        sock.close()


class RinkhalsUiApp(BaseApp):
    app_update_loop_key = 0
    fullscreen = True

    def __init__(self):
        super().__init__()
        
        logging.debug(f'Root: {RINKHALS_ROOT}')
        logging.debug(f'Home: {RINKHALS_HOME}')

    def monitor_k3sysui(self):
        pids = shell("ps | grep K3SysUi | grep -v grep | awk '{print $1}'").split()
        if not pids or not pids[0].isdigit():
            return
        pid = int(pids[0])

        logging.info(f'Monitoring K3SysUi (PID: {pid})')

        while True:
            time.sleep(5)

            try:
                os.kill(pid, 0)
            except OSError:
                logging.info('K3SysUi is gone, exiting...')
                self.quit()
    def monitor_mqtt(self):
        import paho.mqtt.client as paho
        
        def mqtt_on_connect(client, userdata, flags, reason_code, properties):
            client.subscribe(f'anycubic/anycubicCloud/v1/+/printer/{KOBRA_MODEL_ID}/{KOBRA_DEVICE_ID}/print')
            logging.info('Monitoring MQTT...')
        def mqtt_on_connect_fail(client, userdata):
            logging.info('MQTT connection failed')
        def mqtt_on_log(client, userdata, level, buf):
            logging.debug(buf)
        def mqtt_on_message(client, userdata, msg):
            logging.info('Received print event, exiting...')
            self.quit()

        with open('/userdata/app/gk/config/device_account.json', 'r') as f:
            json_data = f.read()
            data = json.loads(json_data)

            mqtt_username = data['username']
            mqtt_password = data['password']

        client = paho.Client(protocol = paho.MQTTv5)
        client.on_connect = mqtt_on_connect
        client.on_connect_fail = mqtt_on_connect_fail
        client.on_message = mqtt_on_message
        client.on_log = mqtt_on_log

        client.username_pw_set(mqtt_username, mqtt_password)
        client.connect('127.0.0.1', 2883)
        client.loop_start()

    def layout(self):
        # The look of every screen follows the home's: the shared styles are
        # built in super().layout(), so they are told first
        if self.screen_info:
            lvr.set_look(home_tools.theme_for(self.screen_info.width, self.screen_info.height))
        super().layout()

        # The home screen uses the whole display (fullscreen = True): the
        # logo panel that used to fill the left half is hidden, its model and
        # version are in the home header and its disk usage in the Info dialog.

        if self.screen_main:
            self.home_theme = 'classic'
            theme = home_tools.theme_for(self.screen_info.width, self.screen_info.height)
            builder = {'aero': self.layout_aero_home, 'liquid': self.layout_liquid_home}.get(theme)
            if builder:
                try:
                    builder()
                    self.home_theme = theme
                except Exception:
                    # A look that fails to build must never leave the printer without a menu
                    logging.exception(f'The {theme} home failed, using Classic')
                    self.screen_main.clean()
            if self.home_theme == 'classic':
                self.layout_classic_home()

        # fireworks_shown = get_app_property('rinkhals_ui', 'fireworks_shown')
        # if not fireworks_shown or fireworks_shown.lower() != 'true':
        #     set_app_property('rinkhals_ui', 'fireworks_shown', 'True')
        #     self.show_fireworks()

        self.show_screen(self.screen_main)
        run_async(self.layout_async)
    def layout_classic_home(self):
        """Classic theme: the flat home screen after branding/ui-mockups/png/Main.png."""
        self.screen_main.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.screen_main.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        self.screen_main.set_style_pad_row(lv.dpx(10), lv.STATE.DEFAULT)
        self.screen_main.set_style_pad_all(lv.dpx(10), lv.STATE.DEFAULT)

        # Home screen after branding/ui-mockups/png/Main.png (Classic theme):
        # header, a 3x2 grid of cards, and a row of three plain buttons.
        SURFACE = lv.color_make(22, 29, 23)
        BORDER = lv.color_make(36, 48, 38)
        ICON_BOX = lv.color_make(31, 42, 33)
        ICON_GREEN = lv.color_make(201, 234, 127)
        PILL = lv.color_make(30, 62, 32)

        def plain(widget):
            widget.remove_flag(lv.OBJ_FLAG.CLICKABLE)
            return widget

        def card(parent, icon, label, hint, callback):
            button = lvr.button(parent)
            button.set_flex_grow(1)
            button.set_height(lv.pct(100))
            button.set_style_min_height(0, lv.STATE.DEFAULT)
            button.set_flex_flow(lv.FLEX_FLOW.COLUMN)
            button.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START)
            button.set_style_pad_all(lv.dpx(10), lv.STATE.DEFAULT)
            button.set_style_pad_row(lv.dpx(2), lv.STATE.DEFAULT)
            button.set_style_radius(lv.dpx(14), lv.STATE.DEFAULT)
            button.set_style_bg_color(SURFACE, lv.STATE.DEFAULT)
            button.set_style_border_color(BORDER, lv.STATE.DEFAULT)
            button.set_icon('')
            button.set_text('')
            box = plain(lvr.panel(button))
            box.set_size(lv.dpx(40), lv.dpx(40))
            box.set_style_pad_all(0, lv.STATE.DEFAULT)
            box.set_style_radius(lv.dpx(12), lv.STATE.DEFAULT)
            box.set_style_bg_color(ICON_BOX, lv.STATE.DEFAULT)
            box.set_style_bg_opa(lv.OPA.COVER, lv.STATE.DEFAULT)
            glyph = lv.label(box)
            glyph.set_text(icon)
            glyph.set_style_text_font(lvr.get_font_icon(), lv.STATE.DEFAULT)
            glyph.set_style_text_color(ICON_GREEN if label in ('Web portal', 'LemSearch Lite') else lvr.COLOR_PRIMARY, lv.STATE.DEFAULT)
            glyph.center()
            plain(lvr.title(button)).set_text(label)
            button.hint = plain(lvr.subtitle(button))
            button.hint.set_text(hint)
            button.add_event_cb(lambda e: callback(), lv.EVENT_CODE.CLICKED, None)
            return button

        def flat(parent, icon, label, callback, color=None):
            button = lvr.button(parent)
            button.set_flex_grow(1)
            button.set_height(lv.dpx(44))
            button.set_style_min_height(0, lv.STATE.DEFAULT)
            button.set_flex_flow(lv.FLEX_FLOW.ROW)
            button.set_style_pad_column(lv.dpx(10), lv.STATE.DEFAULT)
            button.set_style_radius(lv.dpx(12), lv.STATE.DEFAULT)
            button.set_style_bg_color(SURFACE, lv.STATE.DEFAULT)
            button.set_style_border_color(BORDER, lv.STATE.DEFAULT)
            button.set_icon(icon)
            button.set_text(label)
            if color:
                button.set_style_text_color(color, lv.STATE.DEFAULT)
            button.add_event_cb(lambda e: callback(), lv.EVENT_CODE.CLICKED, None)
            return button

        def row_of(parent, height=None):
            row = lvr.panel(parent, flex_flow=lv.FLEX_FLOW.ROW)
            row.set_width(lv.pct(100))
            row.set_style_pad_column(lv.dpx(10), lv.STATE.DEFAULT)
            row.set_style_pad_all(0, lv.STATE.DEFAULT)
            if height:
                row.set_height(height)
            return row

        def show_link(port, name):
            ip = printer_ip()
            if not ip:
                self.show_text_dialog('The printer has no network\naddress right now.')
                return
            self.show_qr_dialog(f'http://{ip}:{port}', f'{name}\nhttp://{ip}:{port}')

        def confirm(text, action):
            self.show_text_dialog(text, action='Yes', callback=action)

        # Header: logo, name, model and address, version pill
        header = row_of(self.screen_main, lv.dpx(40))
        header.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        logo = lvr.image(header)
        logo.set_src(ASSETS_PATH + '/icon.png')
        logo.scale_to(lv.dpx(32))
        title = lvr.title(header)
        title.set_width(lv.SIZE_CONTENT)
        title.set_text('Boomslang')
        gap = plain(lvr.panel(header))
        gap.set_flex_grow(1)
        gap.set_height(1)
        gap.set_style_pad_all(0, lv.STATE.DEFAULT)
        self.home_label_device = lvr.subtitle(header)
        self.home_label_device.set_width(lv.SIZE_CONTENT)
        self.home_label_device.set_text(ellipsis(f'{home_tools.short_model(KOBRA_MODEL)} \u00b7 {printer_ip() or "no network"}', 26))
        pill = plain(lvr.panel(header))
        pill.set_style_pad_hor(lv.dpx(12), lv.STATE.DEFAULT)
        pill.set_style_pad_ver(lv.dpx(4), lv.STATE.DEFAULT)
        pill.set_style_radius(lv.dpx(20), lv.STATE.DEFAULT)
        pill.set_style_bg_color(PILL, lv.STATE.DEFAULT)
        pill.set_style_bg_opa(lv.OPA.COVER, lv.STATE.DEFAULT)
        pill_text = lv.label(pill)
        pill_text.set_text(ellipsis(display_version(RINKHALS_VERSION), 24))
        pill_text.set_style_text_color(lvr.COLOR_PRIMARY, lv.STATE.DEFAULT)
        # Back to the stock Anycubic screen (this used to sit on the logo panel)
        button_exit = lvr.button_icon(header)
        button_exit.set_size(lv.dpx(40), lv.dpx(40))
        button_exit.set_text('')
        button_exit.add_event_cb(lambda e: self.quit(), lv.EVENT_CODE.CLICKED, None)

        # Live status: temperatures and what the printer is doing
        self.home_label_status = lvr.subtitle(self.screen_main)
        self.home_label_status.set_width(lv.pct(100))
        self.home_label_status.set_text('')

        row = row_of(self.screen_main)
        row.set_flex_grow(1)
        row.set_style_min_height(0, lv.STATE.DEFAULT)
        card(row, '\ue5c3', 'Apps', 'Start, stop, configure', lambda: self.show_screen(self.screen_apps))
        card(row, '\ue8d1', 'App Store', 'Browse and install', lambda: self.show_screen(self.screen_store))
        self.home_card_updates = card(row, '\ue62a', 'Updates', 'Boomslang and firmware', lambda: self.show_screen(self.screen_ota))

        row = row_of(self.screen_main)
        row.set_flex_grow(1)
        row.set_style_min_height(0, lv.STATE.DEFAULT)
        card(row, '\ue00a', 'Web portal', 'Open on your phone', lambda: show_link(8090, 'Boomslang web portal'))
        card(row, '\ue894', 'Mainsail', 'Klipper web interface', lambda: show_link(4409, 'Mainsail'))
        card(row, '\ue8b6', 'LemSearch Lite', 'Search and read the web', self.browser_show)

        row = row_of(self.screen_main)
        flat(row, '\uf053', 'Restart', lambda: confirm('Are you sure you want\nto restart Boomslang?', self.restart_rinkhals))
        flat(row, '\ue8ac', 'Reboot', lambda: confirm('Are you sure you want\nto reboot your printer?', self.reboot_printer))
        flat(row, '\ue8b8', 'Settings', lambda: self.show_screen(self.screen_advanced), lvr.COLOR_DANGER)

    # --- Aero theme (branding/ui-mockups/png/Aero.png, design.md) -------------------
    # Glass chrome on a green wallpaper: a back button, a tab with the name and
    # version, a tray, and a taskbar with six orbs and the clock. Drawn for an
    # 800x480 screen, in real pixels (not dpx): the mockups are that size.
    AERO_INK = (20, 58, 24)           # dark green on the light orbs
    AERO_ORB = ((238, 247, 232), (190, 218, 182))
    AERO_ORB_PRESSED = ((176, 208, 168), (150, 186, 142))
    AERO_PILL = ((201, 234, 127), (126, 196, 78))
    AERO_BADGE = (224, 83, 63)

    def home_clear(self, widget, radius=0):
        """No background, border or padding of the default panel style."""
        widget.set_style_bg_opa(lv.OPA.TRANSP, lv.STATE.DEFAULT)
        widget.set_style_border_width(0, lv.STATE.DEFAULT)
        widget.set_style_pad_all(0, lv.STATE.DEFAULT)
        widget.set_style_radius(radius, lv.STATE.DEFAULT)
        widget.remove_flag(lv.OBJ_FLAG.SCROLLABLE)
        return widget

    def aero_glass(self, widget, radius=16):
        """A frosted pane: translucent white with a light edge."""
        widget.set_style_bg_color(lv.color_white(), lv.STATE.DEFAULT)
        widget.set_style_bg_opa(46, lv.STATE.DEFAULT)
        widget.set_style_border_width(1, lv.STATE.DEFAULT)
        widget.set_style_border_color(lv.color_white(), lv.STATE.DEFAULT)
        widget.set_style_border_opa(80, lv.STATE.DEFAULT)
        widget.set_style_radius(radius, lv.STATE.DEFAULT)
        widget.set_style_pad_all(0, lv.STATE.DEFAULT)
        widget.set_style_shadow_width(0, lv.STATE.DEFAULT)
        widget.remove_flag(lv.OBJ_FLAG.SCROLLABLE)
        return widget

    def aero_light(self, widget, colors, radius):
        """A light, rounded, slightly shaded surface (the orbs, the clock)."""
        top, bottom = colors
        widget.set_style_bg_color(lv.color_make(*top), lv.STATE.DEFAULT)
        widget.set_style_bg_grad_color(lv.color_make(*bottom), lv.STATE.DEFAULT)
        widget.set_style_bg_grad_dir(lv.GRAD_DIR.VER, lv.STATE.DEFAULT)
        widget.set_style_bg_opa(lv.OPA.COVER, lv.STATE.DEFAULT)
        widget.set_style_border_width(2, lv.STATE.DEFAULT)
        widget.set_style_border_color(lv.color_white(), lv.STATE.DEFAULT)
        widget.set_style_border_opa(150, lv.STATE.DEFAULT)
        widget.set_style_radius(radius, lv.STATE.DEFAULT)
        widget.set_style_shadow_width(0, lv.STATE.DEFAULT)
        return widget

    def aero_orb(self, parent, x, glyph, callback):
        orb = lvr.button_icon(parent)
        orb.set_size(60, 60)
        orb.set_style_min_width(0, lv.STATE.DEFAULT)   # the button style's minimum (73 px) made the orbs wide pills
        orb.set_pos(x, 408)            # the taskbar is 396..480: 408..468 is centred in it
        self.aero_light(orb, self.AERO_ORB, 30)
        top, bottom = self.AERO_ORB_PRESSED
        orb.set_style_bg_color(lv.color_make(*top), lv.STATE.PRESSED)
        orb.set_style_bg_grad_color(lv.color_make(*bottom), lv.STATE.PRESSED)
        orb.set_style_text_color(lv.color_make(*self.AERO_INK), lv.STATE.DEFAULT)
        orb.set_text(glyph)
        orb.add_event_cb(lambda e: callback(), lv.EVENT_CODE.CLICKED, None)
        return orb

    def home_glyph(self, parent, glyph, x, y, color=(242, 248, 238)):
        label = lv.label(parent)
        label.set_text(glyph)
        label.set_style_text_font(lvr.get_font_icon_small(), lv.STATE.DEFAULT)
        label.set_style_text_color(lv.color_make(*color), lv.STATE.DEFAULT)
        label.set_pos(x, y)
        return label

    def home_show_link(self, port, name):
        ip = printer_ip()
        if not ip:
            self.show_text_dialog('The printer has no network\naddress right now.')
            return
        self.show_qr_dialog(f'http://{ip}:{port}', f'{name}\nhttp://{ip}:{port}')

    def home_power(self):
        options = ['Restart Boomslang', 'Reboot printer', 'Switch to stock']
        if not getattr(self, 'modal_selection', None):
            self.show_text_dialog('Still loading,\ntry again in a moment.')
            return

        def chosen(option):
            if option == options[0]:
                self.show_text_dialog('Are you sure you want\nto restart Boomslang?', action='Yes', callback=self.restart_rinkhals)
            elif option == options[1]:
                self.show_text_dialog('Are you sure you want\nto reboot your printer?', action='Yes', callback=self.reboot_printer)
            else:
                self.show_text_dialog('Are you sure you want\nto switch to stock firmware?\n\nYou can reboot your printer\nto start Boomslang again',
                                      action='Yes', callback=self.stop_rinkhals)
        self.show_selection_dialog(options, chosen)

    def layout_aero_home(self):
        main = self.screen_main
        self.home_clear(main)
        main.set_style_bg_color(lv.color_make(12, 36, 16), lv.STATE.DEFAULT)   # what shows if the wallpaper can't be read
        main.set_style_bg_opa(lv.OPA.COVER, lv.STATE.DEFAULT)

        # Wallpaper: a raw RGB565 LVGL image, so nothing is decoded on redraw
        # (see branding/make-aero-wallpaper.py)
        wallpaper = lvr.image(main)
        wallpaper.set_src(ASSETS_PATH + '/aero-wallpaper.bin')
        wallpaper.set_pos(0, 0)
        wallpaper.remove_flag(lv.OBJ_FLAG.CLICKABLE)

        # Taskbar
        bar = self.home_clear(lvr.panel(main))
        bar.set_size(800, 84)
        bar.set_pos(0, 396)
        bar.set_style_bg_color(lv.color_black(), lv.STATE.DEFAULT)
        bar.set_style_bg_opa(90, lv.STATE.DEFAULT)
        bar.set_style_border_side(lv.BORDER_SIDE.TOP, lv.STATE.DEFAULT)
        bar.set_style_border_width(1, lv.STATE.DEFAULT)
        bar.set_style_border_color(lv.color_white(), lv.STATE.DEFAULT)
        bar.set_style_border_opa(60, lv.STATE.DEFAULT)

        # Orbs: Settings, App Store, Apps, Web portal, LemSearch (the browser), Power
        self.aero_orb(main, 14, '', lambda: self.show_screen(self.screen_advanced))
        self.aero_orb(main, 88, '', lambda: self.show_screen(self.screen_store))
        self.aero_orb(main, 162, '', lambda: self.show_screen(self.screen_apps))
        self.aero_orb(main, 236, '', lambda: self.home_show_link(8090, 'Boomslang web portal'))
        self.aero_orb(main, 310, '', self.browser_show)
        self.aero_orb(main, 384, '', self.home_power)

        # Clock
        clock = self.aero_light(lvr.panel(main), self.AERO_ORB, 10)
        clock.set_size(92, 60)
        clock.set_pos(694, 408)
        clock.remove_flag(lv.OBJ_FLAG.SCROLLABLE)
        clock.set_style_pad_all(0, lv.STATE.DEFAULT)     # the panel's own padding left no room for two lines
        self.home_label_time = lvr.title(clock)
        self.home_label_time.set_style_text_color(lv.color_make(*self.AERO_INK), lv.STATE.DEFAULT)
        self.home_label_time.align(lv.ALIGN.CENTER, 0, -11)
        self.home_label_date = lvr.subtitle(clock)
        self.home_label_date.set_style_text_color(lv.color_make(*self.AERO_INK), lv.STATE.DEFAULT)
        self.home_label_date.align(lv.ALIGN.CENTER, 0, 14)
        self.home_tick_clock()

        # Back: leaves Boomslang for the stock screen (the other screens have
        # their own back buttons, which lead here)
        back = lvr.button_icon(main)
        back.set_size(60, 60)
        back.set_pos(14, 14)
        self.aero_glass(back, 16)
        back.set_style_text_color(lv.color_make(242, 248, 238), lv.STATE.DEFAULT)
        back.set_text('')
        back.add_event_cb(lambda e: self.quit(), lv.EVENT_CODE.CLICKED, None)

        # Tab: logo, name, version and, when there is one, the Update pill
        tab = self.aero_glass(lvr.panel(main), 24)
        tab.set_size(320, 114)
        tab.set_pos(240, -24)

        line = self.home_clear(lvr.panel(tab, flex_flow=lv.FLEX_FLOW.ROW))
        line.set_size(320, 40)
        line.set_pos(0, 32)
        line.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        line.set_style_pad_column(10, lv.STATE.DEFAULT)
        logo = lvr.image(line)
        logo.set_src(ASSETS_PATH + '/icon.png')
        logo.scale_to(30)
        title = lvr.title(line)
        title.set_width(lv.SIZE_CONTENT)
        title.set_text('Boomslang')

        line = self.home_clear(lvr.panel(tab, flex_flow=lv.FLEX_FLOW.ROW))
        line.set_size(320, 34)
        line.set_pos(0, 72)
        line.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        line.set_style_pad_column(10, lv.STATE.DEFAULT)
        version = lvr.subtitle(line)
        version.set_width(lv.SIZE_CONTENT)
        version.set_text(ellipsis(display_version(RINKHALS_VERSION), 24))
        self.home_pill = lvr.button(line)
        self.home_pill.set_height(26)
        self.home_pill.set_width(lv.SIZE_CONTENT)
        self.home_pill.set_style_min_height(0, lv.STATE.DEFAULT)
        self.home_pill.set_style_pad_hor(14, lv.STATE.DEFAULT)
        self.home_pill.set_style_pad_ver(0, lv.STATE.DEFAULT)
        self.aero_light(self.home_pill, self.AERO_PILL, 13)
        self.home_pill.set_style_border_width(0, lv.STATE.DEFAULT)
        self.home_pill.set_style_text_color(lv.color_make(*self.AERO_INK), lv.STATE.DEFAULT)
        self.home_pill.set_icon('')
        self.home_pill.set_text('Update')
        self.home_pill.add_event_cb(lambda e: self.show_screen(self.screen_ota), lv.EVENT_CODE.CLICKED, None)
        self.home_pill.add_flag(lv.OBJ_FLAG.HIDDEN)

        # Tray: network, activity, notifications (an update) and the printer
        tray = self.aero_glass(lvr.panel(main), 16)
        tray.set_size(90, 90)
        tray.set_pos(696, 14)
        self.home_wifi = self.home_glyph(tray, '', 16, 16)
        self.home_glyph(tray, '', 52, 16)
        self.home_glyph(tray, '', 16, 52)
        self.home_glyph(tray, '', 52, 52)
        self.home_badge = self.home_clear(lvr.panel(tray), 8)
        self.home_badge.set_size(16, 16)
        self.home_badge.set_pos(30, 46)
        self.home_badge.set_style_bg_color(lv.color_make(*self.AERO_BADGE), lv.STATE.DEFAULT)
        self.home_badge.set_style_bg_opa(lv.OPA.COVER, lv.STATE.DEFAULT)
        badge_text = lv.label(self.home_badge)
        badge_text.set_text('1')
        badge_text.set_style_text_color(lv.color_white(), lv.STATE.DEFAULT)
        badge_text.center()
        self.home_badge.add_flag(lv.OBJ_FLAG.HIDDEN)

        # What the printer is doing, in the open middle of the screen
        self.home_label_status = lvr.subtitle(main)
        self.home_label_status.set_width(420)
        self.home_label_status.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.STATE.DEFAULT)
        self.home_label_status.set_pos(190, 250)
        self.home_label_status.set_text('')
        self.home_refresh()

    def home_tick_clock(self):
        now = time.localtime()
        self.home_label_time.set_text(time.strftime('%H:%M', now))
        # Short: the full 18/11/2026 is wider than the clock on the printer's screen
        self.home_label_date.set_text(time.strftime('%d %b', now))

    def home_refresh(self):
        """What changes while the UI is open: the clock and whether there is a network."""
        self.home_tick_clock()
        online = printer_ip() is not None
        self.home_wifi.set_style_text_color(lv.color_make(242, 248, 238) if online else lv.color_make(120, 140, 120), lv.STATE.DEFAULT)

    def home_show_update(self, latest):
        """There is a newer release: mark it on whichever home screen is showing."""
        text = ellipsis(f'{display_version(latest.version)} available', 26)
        if self.home_theme != 'classic':
            self.home_pill.remove_flag(lv.OBJ_FLAG.HIDDEN)
            self.home_badge.remove_flag(lv.OBJ_FLAG.HIDDEN)
        else:
            self.home_card_updates.hint.set_text(text)
            self.home_card_updates.hint.set_style_text_color(lvr.COLOR_PRIMARY, lv.STATE.DEFAULT)

    def home_clock_loop(self):
        while True:
            time.sleep(20)
            if self.screen_current in (self.screen_main, self.screen_composition):
                with lvr.lock():
                    self.home_tick_clock()

    # Settings > Look: Classic, Aero or Liquid Plastic. Takes effect when Boomslang opens next.
    def choose_theme(self):
        names = home_tools.THEME_NAMES
        options = [names[theme] for theme in home_tools.THEMES]
        if not getattr(self, 'modal_selection', None):
            self.show_text_dialog('Still loading,\ntry again in a moment.')
            return

        def chosen(option):
            theme = next(t for t in home_tools.THEMES if names[t] == option)
            if theme == self.home_theme:
                return
            try:
                home_tools.set_theme(theme)
            except OSError as e:
                logging.error(f'Could not save the look: {e}')
                self.show_text_dialog('Could not save the choice.\nNothing was changed.')
                return
            self.show_text_dialog(f'The {option} look is used\nthe next time Boomslang opens.\n\nBoomslang closes now.',
                                  callback=self.quit)
        self.show_selection_dialog(options, chosen)

    # --- Liquid Plastic (design.md, branding/make-liquid.py) -----------------------------
    # Clear glass panes. They are part of the wallpaper pictures (LVGL can't blur what
    # is behind a widget); what is built here is the live part on top: touch areas
    # that light up the pane under the finger, the icons, the clock, the text, and
    # the quick settings panel that drops down from the tab. Where everything goes
    # is in liquid_layout.py, which the picture is made from too.
    MUTE_SOUNDS_FILE = '/useremain/rinkhals/.mute-sounds'

    def layout_liquid_home(self):
        L = liquid_layout
        main = self.screen_main
        glass = liquid_ui.Glass(lv, lvr)
        self.home_clear(main)
        main.set_style_bg_color(lv.color_make(6, 23, 12), lv.STATE.DEFAULT)   # what shows if the picture can't be read
        main.set_style_bg_opa(lv.OPA.COVER, lv.STATE.DEFAULT)

        picture = lvr.image(main)
        picture.set_src(ASSETS_PATH + '/liquid-home.bin')
        picture.set_pos(0, 0)
        picture.remove_flag(lv.OBJ_FLAG.CLICKABLE)

        # Touch areas over the panes: the six orbs, back, and the tab (which opens the quick settings)
        actions = (lambda: self.show_screen(self.screen_advanced), lambda: self.show_screen(self.screen_store),
                   lambda: self.show_screen(self.screen_apps), lambda: self.home_show_link(8090, 'Boomslang web portal'),
                   self.browser_show, self.home_power)
        for index, (_name, glyph, _label) in enumerate(L.ORBS):
            glass.touch(main, L.orb_rect(index), L.ORB_SIZE // 2, actions[index], glyph=glyph)
        glass.touch(main, L.BACK, L.BACK_RADIUS, self.quit, glyph=chr(0xe166))
        glass.touch(main, L.TAB_TOUCH, L.TAB_RADIUS, self.liquid_open_panel)

        white = lv.color_make(255, 255, 255)

        # The clock
        clock = glass.container(main, L.CLOCK, clickable=False)
        self.home_label_time = lvr.title(clock)
        self.home_label_time.set_style_text_color(white, lv.STATE.DEFAULT)
        self.home_label_time.align(lv.ALIGN.CENTER, 0, -11)
        self.home_label_date = lvr.subtitle(clock)
        self.home_label_date.set_style_text_color(white, lv.STATE.DEFAULT)
        self.home_label_date.align(lv.ALIGN.CENTER, 0, 14)
        self.home_tick_clock()

        # The tab: logo and name, then the version and, when there is one, the Update pill
        def row(rect):
            line = glass.container(main, rect, clickable=False)
            line.set_flex_flow(lv.FLEX_FLOW.ROW)
            line.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
            line.set_style_pad_column(10, lv.STATE.DEFAULT)
            return line

        line = row(L.TAB_TITLE_ROW)
        logo = lvr.image(line)
        logo.set_src(ASSETS_PATH + '/icon.png')
        logo.scale_to(32)
        title = lvr.title(line)
        title.set_width(lv.SIZE_CONTENT)
        title.set_style_text_color(white, lv.STATE.DEFAULT)
        title.set_text('Boomslang')

        line = row(L.TAB_VERSION_ROW)
        version = lvr.subtitle(line)
        version.set_width(lv.SIZE_CONTENT)
        version.set_style_text_color(white, lv.STATE.DEFAULT)
        version.set_text(ellipsis(display_version(RINKHALS_VERSION), 24))
        self.home_pill = lvr.button(line)
        self.home_pill.set_height(26)
        self.home_pill.set_width(lv.SIZE_CONTENT)
        self.home_pill.set_style_min_height(0, lv.STATE.DEFAULT)
        self.home_pill.set_style_pad_hor(14, lv.STATE.DEFAULT)
        self.home_pill.set_style_pad_ver(0, lv.STATE.DEFAULT)
        self.aero_light(self.home_pill, self.AERO_PILL, 13)
        self.home_pill.set_style_border_width(0, lv.STATE.DEFAULT)
        self.home_pill.set_style_text_color(lv.color_make(*self.AERO_INK), lv.STATE.DEFAULT)
        self.home_pill.set_icon('')
        self.home_pill.set_text('Update')
        self.home_pill.add_event_cb(lambda e: self.show_screen(self.screen_ota), lv.EVENT_CODE.CLICKED, None)
        self.home_pill.add_flag(lv.OBJ_FLAG.HIDDEN)

        # The tray: network, activity, notifications (an update) and the printer
        tx, ty = L.TRAY[0], L.TRAY[1]
        glyphs = ('', '', '', '')
        for index, ((x, y), glyph) in enumerate(zip(L.TRAY_ICONS, glyphs)):
            icon = self.home_glyph(main, glyph, tx + x, ty + y)
            if index == 0:
                self.home_wifi = icon
        self.home_badge = self.home_clear(lvr.panel(main), 9)
        self.home_badge.set_size(18, 18)
        self.home_badge.set_pos(tx + 33, ty + 47)
        self.home_badge.set_style_bg_color(lv.color_make(*self.AERO_BADGE), lv.STATE.DEFAULT)
        self.home_badge.set_style_bg_opa(lv.OPA.COVER, lv.STATE.DEFAULT)
        badge_text = lv.label(self.home_badge)
        badge_text.set_text('1')
        badge_text.set_style_text_color(white, lv.STATE.DEFAULT)
        badge_text.center()
        self.home_badge.add_flag(lv.OBJ_FLAG.HIDDEN)

        # What the printer is doing, in the open middle of the screen
        self.home_label_status = lvr.subtitle(main)
        self.home_label_status.set_width(420)
        self.home_label_status.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.STATE.DEFAULT)
        self.home_label_status.set_style_text_color(white, lv.STATE.DEFAULT)
        self.home_label_status.set_pos(190, 250)
        self.home_label_status.set_text('')

        # The quick settings panel, last: it opens over everything above
        self.layout_liquid_panel(glass, main)
        self.home_refresh()

    def layout_liquid_panel(self, glass, main):
        L = liquid_layout
        panel = liquid_ui.DropPanel(glass, main, ASSETS_PATH + '/liquid-panel.bin',
                                    (L.PANEL[0], 0, L.PANEL[2], L.PANEL_VISIBLE_BOTTOM), L.PANEL_CLOSE,
                                    on_open=self.liquid_panel_refresh)
        self.liquid_panel = panel
        layer = panel.layer

        title = lvr.title(layer)
        title.set_style_text_color(lv.color_make(255, 255, 255), lv.STATE.DEFAULT)
        title.set_text('Quick settings')
        title.set_pos(*L.PANEL_TITLE)

        # Brightness: a dim sun, the slider, a bright sun
        glass.label(layer, '', *L.PANEL_SLIDER_ICONS[0], glyph=True)
        glass.label(layer, '', *L.PANEL_SLIDER_ICONS[1], glyph=True)
        self.liquid_last_brightness = 0.0
        self.liquid_slider = glass.slider(layer, L.PANEL_SLIDER, liquid_ui.MIN_BRIGHTNESS, 100, 100,
                                          on_change=self.liquid_brightness, on_release=lambda v: self.liquid_brightness(v, final=True))

        # Two toggles and two buttons
        self.liquid_sounds = liquid_ui.Toggle(glass, layer, L.PANEL_CHIPS[0], L.PANEL_CHIP_RADIUS, '', 'Sounds',
                                              True, self.liquid_toggle_sounds)
        self.liquid_updates = liquid_ui.Toggle(glass, layer, L.PANEL_CHIPS[1], L.PANEL_CHIP_RADIUS, '', 'Auto update',
                                               True, self.liquid_toggle_updates)
        buttons = (('', 'Web portal', lambda: (panel.hide(), self.home_show_link(8090, 'Boomslang web portal'))),
                   ('', 'Settings', lambda: (panel.hide(), self.show_screen(self.screen_advanced))))
        for rect, (glyph, text, action) in zip(L.PANEL_BUTTONS, buttons):
            glass.chip_label(layer, rect, glyph, text)
            glass.touch(layer, rect, L.PANEL_CHIP_RADIUS, action)

    def liquid_open_panel(self):
        self.liquid_panel.show()

    def liquid_panel_refresh(self):
        """Opening the panel: show what is true now (brightness, sounds and updates can change elsewhere)."""
        percent = liquid_ui.read_brightness()
        if percent is not None:
            self.liquid_slider.set_value(percent, 0)
        self.liquid_sounds.set(not os.path.exists(self.MUTE_SOUNDS_FILE))
        # Reading the property can start a shell (tools.sh), so not on the screen's thread
        run_async(self.liquid_read_updates)

    def liquid_read_updates(self):
        # liquid_auto_update: the setting last read while on, to go back to after Off
        value = get_app_property(self.WEB_APP, 'auto_update')
        if liquid_ui.auto_update_on(value):
            self.liquid_auto_update = value
        with lvr.lock():
            self.liquid_updates.set(liquid_ui.auto_update_on(value))

    def liquid_brightness(self, percent, final=False):
        # Dragging gives many events. Write at most every 50 ms, and always the last value (on release).
        now = time.monotonic()
        if not final and now - self.liquid_last_brightness < 0.05:
            return
        self.liquid_last_brightness = now
        try:
            liquid_ui.set_brightness(percent)
        except OSError as e:
            logging.error(f'Could not set the brightness: {e}')

    def liquid_toggle_sounds(self, on):
        try:
            if on:
                if os.path.exists(self.MUTE_SOUNDS_FILE):
                    os.remove(self.MUTE_SOUNDS_FILE)
            else:
                open(self.MUTE_SOUNDS_FILE, 'wb').close()
        except OSError as e:
            logging.error(f'Could not change the sounds: {e}')
            self.liquid_sounds.set(not on)       # it did not change, so don't say it did

    def liquid_toggle_updates(self, on):
        value = liquid_ui.auto_update_value(on, getattr(self, 'liquid_auto_update', None))

        # tools.sh sets the property: a shell, so not on the screen's thread
        def write():
            try:
                set_app_property(self.WEB_APP, 'auto_update', value)
            except Exception as e:
                logging.error(f'Could not change automatic updates: {e}')
                with lvr.lock():
                    self.liquid_updates.set(not on)       # it did not change, so don't say it did
        run_async(write)

    BUILD_PAUSE = 0.05            # seconds before each background build step
    background_done = False

    @contextlib.contextmanager
    def build_step(self):
        time.sleep(self.BUILD_PAUSE)
        with lvr.lock():
            yield

    def layout_async(self):
        # Everything below used to be built before the first frame, one screen
        # after the other under the LVGL lock, which held the home screen back.
        # Now the home screen is drawn first, and each of these is built in a
        # step of its own with a short pause before it, so that touches and
        # drawing are served in between.
        self.first_frame.wait(15)
        time.sleep(0.2)
        logging.info(f'Startup: the home screen was drawn {seconds_since_launch():.1f} s after the menu was launched')

        with self.build_step():
            self.screen_apps = lvr.panel(self.root_screen)
            if self.screen_apps:
                self.screen_apps.add_flag(lv.OBJ_FLAG.HIDDEN)
                self.screen_apps.set_size(lv.pct(100), lv.pct(100))
                self.screen_apps.set_style_pad_all(0, lv.STATE.DEFAULT)
                self.screen_apps.set_style_pad_top(lvr.get_title_bar_height(), lv.STATE.DEFAULT)

                title_bar = lvr.title_bar(self.screen_apps)
                title_bar.set_y(-lvr.get_title_bar_height())
                
                title = lvr.title(title_bar)
                title.set_text('Manage apps')
                title.center()

                icon_back = lvr.button_icon(title_bar)
                icon_back.set_align(lv.ALIGN.LEFT_MID)
                icon_back.add_event_cb(lambda e: self.show_screen(self.screen_main), lv.EVENT_CODE.CLICKED, None)
                icon_back.set_text('')

                icon_refresh = lvr.button_icon(title_bar)
                icon_refresh.add_event_cb(lambda e: self.show_screen(self.screen_apps), lv.EVENT_CODE.CLICKED, None)
                icon_refresh.set_align(lv.ALIGN.RIGHT_MID)
                icon_refresh.set_text('')

                self.screen_apps.panel_apps = None

        with self.build_step():
            self.screen_app = lvr.panel(self.root_screen)
            if self.screen_app:
                self.screen_app.add_flag(lv.OBJ_FLAG.HIDDEN)
                self.screen_app.set_size(lv.pct(100), lv.pct(100))
                self.screen_app.set_style_pad_all(0, lv.STATE.DEFAULT)
                self.screen_app.set_style_pad_top(lvr.get_title_bar_height(), lv.STATE.DEFAULT)

                title_bar = lvr.title_bar(self.screen_app)
                title_bar.set_y(-lvr.get_title_bar_height())
                
                icon_back = lvr.button_icon(title_bar)
                icon_back.set_align(lv.ALIGN.LEFT_MID)
                icon_back.set_text('')
                icon_back.add_event_cb(lambda e: self.show_screen(self.screen_apps), lv.EVENT_CODE.CLICKED, None)

                self.screen_app.button_refresh = lvr.button_icon(title_bar)
                self.screen_app.button_refresh.set_text('')
                self.screen_app.button_refresh.set_align(lv.ALIGN.RIGHT_MID)
                
                self.screen_app.label_title = lvr.title(title_bar)
                self.screen_app.label_title.center()

                panel_app = lvr.panel(self.screen_app, flex_flow=lv.FLEX_FLOW.COLUMN, flex_align=lv.FLEX_ALIGN.CENTER)
                panel_app.set_size(lv.pct(100), lv.pct(100))

                self.screen_app.label_version = lvr.subtitle(panel_app)
                self.screen_app.label_version.set_text('Version:')
                self.screen_app.label_version.set_style_margin_ver(-lvr.get_global_margin() - lv.dpx(2), lv.STATE.DEFAULT)
                
                self.screen_app.label_path = lvr.subtitle(panel_app)
                self.screen_app.label_path.set_style_max_width(lv.pct(100), lv.STATE.DEFAULT)
                
                self.screen_app.label_description = lvr.subtitle(panel_app)
                self.screen_app.label_description.set_style_text_color(lvr.COLOR_TEXT, lv.STATE.DEFAULT)
                self.screen_app.label_description.set_width(lv.pct(100))
                self.screen_app.label_description.set_long_mode(lv.LABEL_LONG_MODE.WRAP)
                self.screen_app.label_description.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.STATE.DEFAULT)

                panel_stats = lvr.panel(panel_app)
                panel_stats.set_width(lv.pct(100))
                panel_stats.set_flex_flow(lv.FLEX_FLOW.ROW)
                panel_stats.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
                panel_stats.set_style_pad_column(0, lv.STATE.DEFAULT)
                panel_stats.set_style_pad_hor(0, lv.STATE.DEFAULT)
                panel_stats.set_style_pad_ver(lv.dpx(15), lv.STATE.DEFAULT)

                panel_disk = lvr.panel(panel_stats, flex_flow=lv.FLEX_FLOW.COLUMN, flex_align=lv.FLEX_ALIGN.CENTER)
                panel_disk.set_style_pad_row(-lv.dpx(2), lv.STATE.DEFAULT)
                panel_disk.set_width(lv.pct(30))
                panel_disk.set_style_pad_all(0, lv.STATE.DEFAULT)

                label_disk_subtitle = lvr.subtitle(panel_disk)
                label_disk_subtitle.set_text('Disk')
                
                self.screen_app.label_disk = lvr.label(panel_disk)
                self.screen_app.label_disk.set_text('?')
                
                panel_memory = lvr.panel(panel_stats, flex_flow=lv.FLEX_FLOW.COLUMN, flex_align=lv.FLEX_ALIGN.CENTER)
                panel_memory.set_style_pad_row(-lv.dpx(2), lv.STATE.DEFAULT)
                panel_memory.set_width(lv.pct(30))
                panel_memory.set_style_pad_all(0, lv.STATE.DEFAULT)

                label_memory_subtitle = lvr.subtitle(panel_memory)
                label_memory_subtitle.set_text('Memory')
                
                self.screen_app.label_memory = lvr.label(panel_memory)
                self.screen_app.label_memory.set_text('?')
                
                panel_cpu = lvr.panel(panel_stats, flex_flow=lv.FLEX_FLOW.COLUMN, flex_align=lv.FLEX_ALIGN.CENTER)
                panel_cpu.set_style_pad_row(-lv.dpx(2), lv.STATE.DEFAULT)
                panel_cpu.set_width(lv.pct(30))
                panel_cpu.set_style_pad_all(0, lv.STATE.DEFAULT)

                label_cpu_subtitle = lvr.subtitle(panel_cpu)
                label_cpu_subtitle.set_text('CPU')
                
                self.screen_app.label_cpu = lvr.label(panel_cpu)
                self.screen_app.label_cpu.set_text('?')
                
                panel_actions = lvr.panel(panel_app)
                panel_actions.set_height(lv.SIZE_CONTENT)
                panel_actions.set_width(lv.pct(100))
                panel_actions.set_flex_flow(lv.FLEX_FLOW.ROW_REVERSE)
                panel_actions.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
                panel_actions.set_style_pad_column(lvr.get_global_margin(), lv.STATE.DEFAULT)
                panel_actions.set_style_pad_all(0, lv.STATE.DEFAULT)
                
                self.screen_app.button_qrcode = lvr.button(panel_actions)
                self.screen_app.button_qrcode.set_icon('')
                
                self.screen_app.button_settings = lvr.button(panel_actions)
                self.screen_app.button_settings.set_icon('')

                self.screen_app.button_toggle_enabled = lvr.button(panel_actions)
                self.screen_app.button_toggle_enabled.set_text('Enable/Disable app')
                self.screen_app.button_toggle_enabled.set_flex_grow(1)
                
                self.screen_app.button_toggle_started = lvr.button(panel_app)
                self.screen_app.button_toggle_started.set_text('Start/Stop app')
                self.screen_app.button_toggle_started.set_width(lv.pct(100))

        with self.build_step():
            self.screen_app_settings = lvr.panel(self.root_screen)
            if self.screen_app_settings:
                self.screen_app_settings.add_flag(lv.OBJ_FLAG.HIDDEN)
                self.screen_app_settings.set_size(lv.pct(100), lv.pct(100))
                self.screen_app_settings.set_style_pad_all(0, lv.STATE.DEFAULT)
                self.screen_app_settings.set_style_pad_top(lvr.get_title_bar_height(), lv.STATE.DEFAULT)

                title_bar = lvr.title_bar(self.screen_app_settings)
                title_bar.set_y(-lvr.get_title_bar_height())
                
                self.screen_app_settings.label_title = lvr.title(title_bar)
                self.screen_app_settings.label_title.center()

                self.screen_app_settings.button_back = lvr.button_icon(title_bar)
                self.screen_app_settings.button_back.set_align(lv.ALIGN.LEFT_MID)
                self.screen_app_settings.button_back.set_text('')

                self.screen_app_settings.button_refresh = lvr.button_icon(title_bar)
                self.screen_app_settings.button_refresh.set_align(lv.ALIGN.RIGHT_MID)
                self.screen_app_settings.button_refresh.set_text('')

                self.screen_app_settings.panel_properties = None

        with self.build_step():
            self.screen_advanced = lvr.panel(self.root_screen)
            if self.screen_advanced:
                self.screen_advanced.add_flag(lv.OBJ_FLAG.HIDDEN)
                self.screen_advanced.set_size(lv.pct(100), lv.pct(100))
                self.screen_advanced.set_style_pad_hor(0, lv.STATE.DEFAULT)
                self.screen_advanced.set_style_pad_top(lvr.get_title_bar_height(), lv.STATE.DEFAULT)
                
                title_bar = lvr.title_bar(self.screen_advanced)
                title_bar.add_flag(lv.OBJ_FLAG.IGNORE_LAYOUT)
                title_bar.set_y(-lvr.get_title_bar_height())

                icon_back = lvr.button_icon(title_bar)
                icon_back.set_align(lv.ALIGN.LEFT_MID)
                icon_back.set_text('')
                icon_back.add_event_cb(lambda e: self.show_screen(self.screen_main), lv.EVENT_CODE.CLICKED, None)
                
                title = lvr.title(title_bar)
                title.set_text('Settings')
                title.center()

                panel_buttons = lvr.panel(self.screen_advanced, flex_flow=lv.FLEX_FLOW.COLUMN)
                panel_buttons.set_size(lv.pct(100), lv.pct(100))

                MUTE_SOUNDS_FILE = '/useremain/rinkhals/.mute-sounds'

                panel_sounds = lvr.panel(panel_buttons)
                panel_sounds.set_width(lv.pct(100))
                panel_sounds.set_style_pad_all(0, lv.STATE.DEFAULT)

                label_sounds = lvr.button(panel_sounds)
                label_sounds.set_width(lv.pct(100))
                label_sounds.set_text('Sounds')
                label_sounds.set_style_pad_left(lv.dpx(15), lv.STATE.DEFAULT)
                label_sounds.set_style_pad_right(lv.dpx(4), lv.STATE.DEFAULT)
                label_sounds.set_style_text_align(lv.TEXT_ALIGN.LEFT, lv.STATE.DEFAULT)

                checkbox_sounds = lvr.checkbox(panel_sounds)
                checkbox_sounds.align(lv.ALIGN.RIGHT_MID, -lv.dpx(5), 0)
                checkbox_sounds.set_checked(not os.path.exists(MUTE_SOUNDS_FILE))

                def toggle_sounds(e, checkbox=checkbox_sounds):
                    try:
                        if os.path.exists(MUTE_SOUNDS_FILE):
                            os.remove(MUTE_SOUNDS_FILE)
                        else:
                            open(MUTE_SOUNDS_FILE, 'wb').close()
                    except OSError as ex:
                        logging.error('Failed to toggle sounds: %s', ex)
                    checkbox.set_checked(not os.path.exists(MUTE_SOUNDS_FILE))

                checkbox_sounds.add_event_cb(toggle_sounds, lv.EVENT_CODE.CLICKED, None)
                label_sounds.add_event_cb(toggle_sounds, lv.EVENT_CODE.CLICKED, None)

                button_reboot = lvr.button(panel_buttons)
                button_reboot.set_width(lv.pct(100))
                button_reboot.set_text('Reboot printer')
                button_reboot.add_event_cb(lambda e: self.show_text_dialog('Are you sure you want\nto reboot your printer?', action='Yes', callback=lambda: self.reboot_printer()), lv.EVENT_CODE.CLICKED, None)
                
                button_info = lvr.button(panel_buttons)
                button_info.set_width(lv.pct(100))
                button_info.set_text('Info')
                button_info.add_event_cb(lambda e: self.show_info_dialog(), lv.EVENT_CODE.CLICKED, None)

                button_restart = lvr.button(panel_buttons)
                button_restart.set_width(lv.pct(100))
                button_restart.set_text('Restart Boomslang')
                button_restart.add_event_cb(lambda e: self.show_text_dialog('Are you sure you want\nto restart Boomslang?', action='Yes', callback=lambda: self.restart_rinkhals()), lv.EVENT_CODE.CLICKED, None)
                
                button_stock = lvr.button(panel_buttons)
                button_stock.set_width(lv.pct(100))
                button_stock.set_text('Switch to stock')
                button_stock.add_event_cb(lambda e: self.show_text_dialog('Are you sure you want\nto switch to stock firmware?\n\nYou can reboot your printer\nto start Boomslang again', action='Yes', callback=lambda: self.stop_rinkhals()), lv.EVENT_CODE.CLICKED, None)

                button_disable = lvr.button(panel_buttons)
                button_disable.set_width(lv.pct(100))
                button_disable.set_style_text_color(lvr.COLOR_DANGER, lv.STATE.DEFAULT)
                button_disable.set_text('Disable Boomslang')
                button_disable.add_event_cb(lambda e: self.show_text_dialog('Are you sure you want\nto disable Boomslang?\n\nYou will need to reinstall\nBoomslang to start it again', action='Yes', action_color=lvr.COLOR_DANGER, callback=lambda: self.disable_rinkhals()), lv.EVENT_CODE.CLICKED, None)

                def setting(label, key, options):
                    # A button showing a Boomslang Web setting; a tap picks another value
                    button = lvr.button(panel_buttons)
                    button.set_width(lv.pct(100))

                    def refresh():
                        button.set_text(f'{label}: {get_app_property(self.WEB_APP, key) or options[0]}')

                    def chosen(value):
                        set_app_property(self.WEB_APP, key, value)
                        refresh()
                    button.add_event_cb(lambda e: self.show_selection_dialog(options, chosen), lv.EVENT_CODE.CLICKED, None)
                    refresh()
                    return button

                setting('Automatic updates', 'auto_update', ['auto', 'off', 'release', 'release-preview', 'beta', 'alpha'])
                setting('Update hours', 'auto_update_hours', ['any', '00-06', '02-06', '22-06', '09-17'])

                self.button_notifications = lvr.button(panel_buttons)
                self.button_notifications.set_width(lv.pct(100))
                self.button_notifications.add_event_cb(lambda e: self.notifications_tap(), lv.EVENT_CODE.CLICKED, None)
                self.notifications_refresh()

                if home_tools.aero_possible(self.screen_info.width, self.screen_info.height):
                    button_theme = lvr.button(panel_buttons)
                    button_theme.set_width(lv.pct(100))
                    button_theme.set_text(f'Look: {home_tools.THEME_NAMES[self.home_theme]}')
                    button_theme.add_event_cb(lambda e: self.choose_theme(), lv.EVENT_CODE.CLICKED, None)

                button_previous = lvr.button(panel_buttons)
                button_previous.set_width(lv.pct(100))
                button_previous.set_text('Go back to previous version')
                button_previous.add_event_cb(lambda e: self.previous_version_tap(), lv.EVENT_CODE.CLICKED, None)

                button_switch = lvr.button(panel_buttons)
                button_switch.set_width(lv.pct(100))
                button_switch.set_style_text_color(lvr.COLOR_DANGER, lv.STATE.DEFAULT)
                button_switch.set_text('Switch to Rinkhals')
                button_switch.add_event_cb(lambda e: self.switch_to_rinkhals_start(), lv.EVENT_CODE.CLICKED, None)

        with self.build_step():
            self.layout_ota()
        with self.build_step():
            self.layout_ota_rinkhals()
        with self.build_step():
            self.layout_ota_firmware()
        with self.build_step():
            self.layout_app_store()
        with self.build_step():
            self.layout_browser()

        with self.build_step():
            self.modal_selection = lvr.modal(self.root_modal)
            if self.modal_selection:
                self.modal_selection.panel_selection = None

            self.modal_text_input = lvr.panel(self.root_modal)
            if self.modal_text_input:
                self.modal_text_input.add_flag(lv.OBJ_FLAG.HIDDEN)
                self.modal_text_input.set_size(lv.pct(100), lv.pct(100))
                self.modal_text_input.set_style_pad_all(0, lv.STATE.DEFAULT)
                self.modal_text_input.set_style_bg_color(lvr.COLOR_BACKGROUND, lv.STATE.DEFAULT)
                self.modal_text_input.set_style_bg_opa(lv.OPA.COVER, lv.STATE.DEFAULT)
                self.modal_text_input.panel_content = None

        self.home_start_background()
        self.background_done = True
        logging.info(f'Startup: every screen is built {seconds_since_launch():.1f} s after the menu was launched')

    def show_screen(self, screen):
        if screen is None:
            # The other screens are built in the background after the home
            # screen is up (layout_async); this one is not ready yet
            self.show_text_dialog('Still loading,\ntry again in a moment.')
            return
        super().show_screen(screen)

        if screen == self.screen_main: self.show_main()
        elif screen == self.screen_apps: self.show_apps()
        elif screen == self.screen_store: self.show_app_store()
    def show_main(self):
        # The address can change while the UI is open (Wi-Fi reconnects)
        if self.home_theme != 'classic':
            self.home_refresh()
        else:
            self.home_label_device.set_text(ellipsis(f'{home_tools.short_model(KOBRA_MODEL)} · {printer_ip() or "no network"}', 26))
    def show_apps(self):
        """Installed apps: name, whether it runs and its version, a switch, and its settings."""
        if self.screen_apps.panel_apps:
            self.screen_apps.panel_apps.delete()
        self.screen_apps.panel_apps = lvr.panel(self.screen_apps, flex_flow=lv.FLEX_FLOW.COLUMN)
        self.screen_apps.panel_apps.set_size(lv.pct(100), lv.pct(100))
        self.screen_apps.panel_apps.set_style_pad_row(0, lv.STATE.DEFAULT)
        panel_apps = self.screen_apps.panel_apps

        self.apps_generation = getattr(self, 'apps_generation', 0) + 1
        generation = self.apps_generation

        def current():
            return generation == self.apps_generation

        self.app_checkboxes = {}
        self.app_status_labels = {}

        def manifest_of(app):
            try:
                with open(f'{get_app_root(app)}/app.json', 'r') as f:
                    return json.loads(f.read(), cls = JSONWithCommentsDecoder)
            except Exception:
                return {}

        def status_of(app, manifest):
            enabled = is_app_enabled(app) == '1'
            started = get_app_status(app) == 'started'
            return enabled, app_settings.status_text(enabled, started, manifest.get('version'))

        def toggle_app(app, on, manifest):
            # enable/start can take seconds (start waits for the app): not on the screen's thread
            def work():
                try:
                    if on:
                        logging.info(f'Enabling {app}...')
                        enable_app(app)
                        if get_app_status(app) != 'started':
                            logging.info(f'Starting {app}...')
                            start_app(app, 5)
                    else:
                        logging.info(f'Disabling {app}...')
                        disable_app(app)
                        if get_app_status(app) == 'started':
                            logging.info(f'Stopping {app}...')
                            stop_app(app)
                except Exception as e:
                    logging.error(f'Could not change {app}: {e}')
                enabled, status = status_of(app, manifest)
                with lvr.lock():
                    if current():
                        self.app_checkboxes[app].set_checked(enabled)
                        self.app_status_labels[app].set_text(status)
            with lvr.lock():
                self.app_status_labels[app].set_text('Starting...' if on else 'Stopping...')
            run_async(work)

        def refresh_apps():
            apps = [ a for a in list_apps().split(' ') if a ]
            for app in apps:
                manifest = manifest_of(app)
                name = str(manifest.get('name') or re.sub(r'^[0-9]+-', '', app))   # "Fluidd", not "26-fluidd"
                enabled, status = status_of(app, manifest)
                has_settings = any(row['kind'] in app_settings.EDITABLE
                                   for row in app_settings.setting_rows(manifest.get('properties'), lambda k: ''))

                with lvr.lock():
                    if not current():
                        return
                    line = lvr.panel(panel_apps)
                    line.set_width(lv.pct(100))
                    line.set_style_min_height(lv.dpx(80), lv.STATE.DEFAULT)
                    line.set_style_border_side(lv.BORDER_SIDE.BOTTOM, lv.STATE.DEFAULT)
                    line.set_flex_flow(lv.FLEX_FLOW.ROW)
                    line.set_flex_align(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
                    line.set_style_pad_column(lvr.get_global_margin(), lv.STATE.DEFAULT)
                    line.remove_flag(lv.OBJ_FLAG.SCROLLABLE)
                    line.set_state(lv.STATE.DISABLED, False)
                    line.add_event_cb(lambda e, app=app: self.show_app(app), lv.EVENT_CODE.CLICKED, None)

                    text = lvr.panel(line, flex_flow=lv.FLEX_FLOW.COLUMN)
                    text.set_style_pad_all(0, lv.STATE.DEFAULT)
                    text.set_style_pad_row(lv.dpx(2), lv.STATE.DEFAULT)
                    text.set_flex_grow(1)
                    text.remove_flag(lv.OBJ_FLAG.CLICKABLE)
                    label_name = lvr.label(text)
                    label_name.set_text(ellipsis(name, 30))
                    label_status = lvr.subtitle(text)
                    label_status.set_text(status)
                    self.app_status_labels[app] = label_status

                    if has_settings:
                        button_settings = lvr.button_icon(line)
                        button_settings.set_text('\ue8b8')
                        button_settings.set_size(lv.dpx(58), lv.dpx(58))
                        button_settings.set_style_min_width(0, lv.STATE.DEFAULT)
                        button_settings.add_event_cb(lambda e, app=app: self.show_app_settings(app), lv.EVENT_CODE.CLICKED, None)

                    switch_app = lvr.switch(line)
                    switch_app.set_checked(enabled)
                    switch_app.add_event_cb(lambda e, app=app, s=switch_app, m=manifest: toggle_app(app, s.get_checked(), m),
                                            lv.EVENT_CODE.VALUE_CHANGED, None)
                    self.app_checkboxes[app] = switch_app

        run_async(refresh_apps)
    def show_app(self, app):
        self.show_screen(self.screen_app)
        
        if isinstance(app, lv.event):
            app = app.get_user_data()

        app_root = get_app_root(app)
        if not os.path.exists(f'{app_root}/app.sh'):
            self.panel_screen.components = [ self.panel_apps ]
            self.layout_apps()
            self.screen.layout()

        app_manifest = None
        if os.path.exists(f'{app_root}/app.json'):
            try:
                with open(f'{app_root}/app.json', 'r') as f:
                    app_manifest = json.loads(f.read(), cls = JSONWithCommentsDecoder)
            except Exception as e:
                pass

        app_name = app_manifest.get('name') if app_manifest else app
        app_description = app_manifest.get('description') if app_manifest else ''
        app_version = app_manifest.get('version') if app_manifest else ''
        app_properties = app_manifest.get('properties', []) if app_manifest else []

        self.screen_app.label_title.set_text(ellipsis(app_name, 24))
        self.screen_app.label_version.set_text(f'Version: {app_version}')
        self.screen_app.label_path.set_text(ellipsis(app_root, 36))
        self.screen_app.label_description.set_text(app_description)
        self.screen_app.label_disk.set_text('-')
        self.screen_app.label_memory.set_text('-')
        self.screen_app.label_cpu.set_text('-')

        self.screen_app.button_refresh.clear_event_cb()
        self.screen_app.button_refresh.add_event_cb(lambda e, app=app: self.show_app(app), lv.EVENT_CODE.CLICKED, None)

        self.screen_app.button_qrcode.add_flag(lv.OBJ_FLAG.HIDDEN)
        
        if len(app_properties) == 0:
            self.screen_app.button_settings.add_flag(lv.OBJ_FLAG.HIDDEN)
        else:
            self.screen_app.button_settings.remove_flag(lv.OBJ_FLAG.HIDDEN)
            self.screen_app.button_settings.clear_event_cb()
            self.screen_app.button_settings.add_event_cb(lambda e, app=app: self.show_app_settings(app), lv.EVENT_CODE.CLICKED, None)

        def update_app_size(result):
            lv.lock()
            self.screen_app.label_disk.set_text(result)
            lv.unlock()
        if USING_SHELL:
            shell_async(f"du -sh {app_root} | awk '{{print $1}}'", update_app_size)
            
        def update_info(app=app):
            app_enabled = is_app_enabled(app) == '1'
            app_status = get_app_status(app)
            app_started = app_status != 'stopped'
            
            # Update the enable app button
            with lvr.lock():
                self.screen_app.button_toggle_enabled.set_text('Disable app' if app_enabled else 'Enable app')
                self.screen_app.button_toggle_enabled.clear_event_cb()
                if app_enabled:
                    self.screen_app.button_toggle_enabled.add_event_cb(lambda e, app=app: self.disable_app(app), lv.EVENT_CODE.CLICKED, app)
                else:
                    self.screen_app.button_toggle_enabled.add_event_cb(lambda e, app=app: self.enable_app(app), lv.EVENT_CODE.CLICKED, app)
        
            # Update the start app button
            with lvr.lock():
                self.screen_app.button_toggle_started.set_text('Stop app' if app_started else 'Start app')
                self.screen_app.button_toggle_started.set_style_text_color(lvr.COLOR_DANGER if app_started else lvr.COLOR_TEXT, lv.STATE.DEFAULT)
                self.screen_app.button_toggle_started.clear_event_cb()
                if app_started:
                    self.screen_app.button_toggle_started.add_event_cb(lambda e, app=app: self.stop_app(app), lv.EVENT_CODE.CLICKED, app)
                else:
                    self.screen_app.button_toggle_started.add_event_cb(lambda e, app=app: self.start_app(app), lv.EVENT_CODE.CLICKED, app)
        
            # Refresh the QR code button if available
            with lvr.lock():
                self.screen_app.button_qrcode.add_flag(lv.OBJ_FLAG.HIDDEN)

            with lvr.lock():
                qr_properties = [ p for p in app_properties if app_properties[p]['type'] == 'qr' ]
                if qr_properties:
                    qr_property = qr_properties[0]
                    display = app_properties[qr_property].get('display')
                    content = get_app_property(app, qr_property)
                    if content:
                        self.screen_app.button_qrcode.remove_flag(lv.OBJ_FLAG.HIDDEN)
                        self.screen_app.button_qrcode.clear_event_cb()
                        self.screen_app.button_qrcode.add_event_cb(lambda e, content=content: self.show_qr_dialog(content, display), lv.EVENT_CODE.CLICKED, None)
                    else:
                        self.screen_app.button_qrcode.add_flag(lv.OBJ_FLAG.HIDDEN)
                else:
                    self.screen_app.button_qrcode.add_flag(lv.OBJ_FLAG.HIDDEN)
        def update_stats(app=app):
            import psutil

            app_pids = get_app_pids(app)
            if not app_pids:
                with lvr.lock():
                    self.screen_app.label_memory.set_text('-')
                    self.screen_app.label_cpu.set_text('-')
                return
            
            app_pids = app_pids.split(' ')
            app_memory = 0
            app_cpu = 0

            for pid in app_pids:
                try:
                    p = psutil.Process(int(pid))
                    app_memory += p.memory_info().rss / 1024 / 1024
                except:
                    continue

            if app_memory == 0:
                with lvr.lock():
                    self.screen_app.label_memory.set_text('-')
                    self.screen_app.label_cpu.set_text('-')
                return

            with lvr.lock():
                self.screen_app.label_memory.set_text(f'{round(app_memory, 1)}M')

            for pid in app_pids:
                try:
                    p = psutil.Process(int(pid))
                    app_cpu += p.cpu_percent(interval=1)
                except:
                    continue
            with lvr.lock():
                self.screen_app.label_cpu.set_text(f'{round(app_cpu, 1)}%')

        self.app_update_loop_key += 1
        def update_loop(key=self.app_update_loop_key * 1):
            while True:
                update_info()

                time.sleep(2)
                if self.screen_current != self.screen_app or key != self.app_update_loop_key:
                    break
                
                update_info()
                update_stats()

                time.sleep(2)
                if self.screen_current != self.screen_app or key != self.app_update_loop_key:
                    break
        run_async(update_loop)
    def show_app_settings(self, app):
        """The settings of an app, from the properties in its app.json (see app_settings.py).

        Every row can be tapped. On/off settings are switches, numbers have - and +,
        choices and text open a list or a keyboard. Advanced settings are folded
        away. A change to a running app offers to restart it, because apps read
        their settings when they start.
        """
        self.show_screen(self.screen_app_settings)

        app_manifest = None
        try:
            with open(f'{get_app_root(app)}/app.json', 'r') as f:
                app_manifest = json.loads(f.read(), cls = JSONWithCommentsDecoder)
        except Exception:
            pass

        app_name = (app_manifest or {}).get('name') or app
        self.screen_app_settings.label_title.set_text(ellipsis(app_name, 24))

        self.screen_app_settings.button_back.clear_event_cb()
        self.screen_app_settings.button_back.add_event_cb(lambda e, app=app: self.show_app(app), lv.EVENT_CODE.CLICKED, None)

        self.screen_app_settings.button_refresh.clear_event_cb()
        self.screen_app_settings.button_refresh.add_event_cb(lambda e, app=app: self.show_app_settings(app), lv.EVENT_CODE.CLICKED, None)

        if self.screen_app_settings.panel_properties:
            self.screen_app_settings.panel_properties.delete()
        panel = lvr.panel(self.screen_app_settings, flex_flow=lv.FLEX_FLOW.COLUMN)
        panel.set_size(lv.pct(100), lv.pct(100))
        panel.set_style_pad_row(0, lv.STATE.DEFAULT)
        panel.set_style_pad_all(0, lv.STATE.DEFAULT)
        self.screen_app_settings.panel_properties = panel

        # Background work below must not touch this panel once it was rebuilt
        self.app_settings_generation = getattr(self, 'app_settings_generation', 0) + 1
        generation = self.app_settings_generation

        def current():
            return generation == self.app_settings_generation

        rows = app_settings.setting_rows((app_manifest or {}).get('properties'), lambda key: get_app_property(app, key))
        basic, advanced = app_settings.split_advanced(rows)

        # Shown when a setting changed while the app runs
        button_restart = lvr.button(panel)
        button_restart.set_width(lv.pct(100))
        button_restart.set_style_margin_all(lvr.get_global_margin(), lv.STATE.DEFAULT)
        button_restart.set_text('Restart the app to use the new settings')
        button_restart.set_style_text_color(lvr.COLOR_PRIMARY, lv.STATE.DEFAULT)
        button_restart.add_flag(lv.OBJ_FLAG.HIDDEN)

        def offer_restart():
            def check():
                running = get_app_status(app) != 'stopped'
                with lvr.lock():
                    if current() and running:
                        button_restart.set_text('Restart the app to use the new settings')
                        button_restart.remove_flag(lv.OBJ_FLAG.HIDDEN)
            run_async(check)

        def restart():
            button_restart.set_text('Restarting...')
            def work():
                try:
                    stop_app(app)
                    start_app(app, 5)
                    text = 'Restarted with the new settings'
                except Exception as e:
                    logging.error(f'Could not restart {app}: {e}')
                    text = 'The restart failed'
                with lvr.lock():
                    if current():
                        button_restart.set_text(text)
            run_async(work)
        button_restart.add_event_cb(lambda e: restart(), lv.EVENT_CODE.CLICKED, None)

        def save(key, value):
            # tools.sh writes the setting: a shell, so not on the screen's thread
            def work():
                try:
                    set_app_property(app, key, value)
                except Exception as e:
                    logging.error(f'Could not save {app} {key}: {e}')
            run_async(work)
            offer_restart()

        if not rows:
            label_none = lvr.subtitle(panel)
            label_none.set_text('This app has no settings.')
            label_none.set_style_margin_all(lvr.get_global_margin(), lv.STATE.DEFAULT)

        for row in basic:
            self.app_setting_row(panel, row, save)

        if advanced:
            button_advanced = lvr.button(panel)
            button_advanced.set_width(lv.pct(100))
            button_advanced.set_style_margin_all(lvr.get_global_margin(), lv.STATE.DEFAULT)
            panel_advanced = lvr.panel(panel, flex_flow=lv.FLEX_FLOW.COLUMN)
            panel_advanced.set_width(lv.pct(100))
            panel_advanced.set_style_pad_all(0, lv.STATE.DEFAULT)
            panel_advanced.set_style_pad_row(0, lv.STATE.DEFAULT)
            panel_advanced.add_flag(lv.OBJ_FLAG.HIDDEN)
            for row in advanced:
                self.app_setting_row(panel_advanced, row, save)

            def toggle_advanced():
                hidden = panel_advanced.has_flag(lv.OBJ_FLAG.HIDDEN)
                if hidden:
                    panel_advanced.remove_flag(lv.OBJ_FLAG.HIDDEN)
                else:
                    panel_advanced.add_flag(lv.OBJ_FLAG.HIDDEN)
                button_advanced.set_text(('Hide' if hidden else 'Show') + f' advanced settings ({len(advanced)})')
            button_advanced.set_text(f'Show advanced settings ({len(advanced)})')
            button_advanced.add_event_cb(lambda e: toggle_advanced(), lv.EVENT_CODE.CLICKED, None)

        if any(row['kind'] in app_settings.EDITABLE for row in rows):
            def reset_default(app=app):
                clear_app_properties(app)
                self.show_app_settings(app)
                offer_restart()

            button_reset = lvr.button(panel)
            button_reset.set_style_margin_all(lvr.get_global_margin(), lv.STATE.DEFAULT)
            button_reset.set_width(lv.pct(100))
            button_reset.set_text('Reset to default')
            button_reset.add_event_cb(lambda e: reset_default(), lv.EVENT_CODE.CLICKED, None)

    def app_setting_row(self, parent, row, save):
        """One setting: its name and value on the left, its control on the right."""
        kind = row['kind']

        line = lvr.panel(parent)
        line.set_width(lv.pct(100))
        line.set_style_min_height(lv.dpx(76), lv.STATE.DEFAULT)
        line.set_style_border_side(lv.BORDER_SIDE.BOTTOM, lv.STATE.DEFAULT)
        line.set_flex_flow(lv.FLEX_FLOW.ROW)
        line.set_flex_align(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        line.set_style_pad_column(lvr.get_global_margin(), lv.STATE.DEFAULT)
        line.remove_flag(lv.OBJ_FLAG.SCROLLABLE)

        text = lvr.panel(line, flex_flow=lv.FLEX_FLOW.COLUMN)
        text.set_style_pad_all(0, lv.STATE.DEFAULT)
        text.set_style_pad_row(lv.dpx(2), lv.STATE.DEFAULT)
        text.set_flex_grow(1)
        text.remove_flag(lv.OBJ_FLAG.CLICKABLE)     # taps go to the row

        label_title = lvr.label(text)
        label_title.set_width(lv.pct(100))
        label_title.set_long_mode(lv.LABEL_LONG_MODE.WRAP)
        label_title.set_text(row['title'])

        label_value = lvr.subtitle(text)
        label_value.set_width(lv.pct(100))
        label_value.set_long_mode(lv.LABEL_LONG_MODE.WRAP)
        label_value.set_text(app_settings.value_text(row))

        def set_value(value):
            row['value'] = str(value)
            label_value.set_text(app_settings.value_text(row))
            save(row['key'], row['value'])

        def tappable(action):
            line.set_state(lv.STATE.DISABLED, False)
            line.add_event_cb(lambda e: action(), lv.EVENT_CODE.CLICKED, None)

        def small_button(glyph, action):
            button = lvr.button_icon(line)
            button.set_text(glyph)
            button.set_size(lv.dpx(58), lv.dpx(58))
            button.set_style_min_width(0, lv.STATE.DEFAULT)     # else the button style widens it
            button.add_event_cb(lambda e: action(), lv.EVENT_CODE.CLICKED, None)
            return button

        if kind == 'switch':
            label_value.add_flag(lv.OBJ_FLAG.HIDDEN)
            control = lvr.switch(line)
            control.set_checked(app_settings.is_on(row['value']))
            changed = lambda on: set_value(app_settings.switch_value(row['options'], on))   # noqa: E731
            control.add_event_cb(lambda e: changed(control.get_checked()), lv.EVENT_CODE.VALUE_CHANGED, None)

            def flip():
                control.set_checked(not control.get_checked())
                changed(control.get_checked())
            tappable(flip)
        elif kind == 'choice':
            small_button('\ue5cc', lambda: self.show_selection_dialog(row['options'], set_value))    # chevron
            tappable(lambda: self.show_selection_dialog(row['options'], set_value))
        elif kind == 'number':
            small_button('\ue15b', lambda: set_value(app_settings.step_number(row['value'], -1)))  # remove
            small_button('\ue145', lambda: set_value(app_settings.step_number(row['value'], 1)))   # add
            tappable(lambda: self.show_input_text_dialog(row['title'], row['value'], True, set_value))
        elif kind == 'text':
            small_button('\ue3c9', lambda: self.show_input_text_dialog(row['title'], row['value'], False, set_value))  # edit
            tappable(lambda: self.show_input_text_dialog(row['title'], row['value'], False, set_value))
        elif kind == 'qr':
            label_value.set_long_mode(lv.LABEL_LONG_MODE.DOTS)
            show = lambda: self.show_qr_dialog(row['value'], row['title'])   # noqa: E731
            small_button('\uef6b', show)
            tappable(show)
        return line

    def show_input_text_dialog(self, title, initial_value, is_number, select_callback=None):
        if self.modal_text_input.panel_content:
            self.modal_text_input.panel_content.delete()

        self.modal_text_input.panel_content = lvr.panel(self.modal_text_input)
        self.modal_text_input.panel_content.set_size(lv.pct(100), lv.pct(100))
        self.modal_text_input.panel_content.set_style_pad_all(lv.dpx(10), lv.STATE.DEFAULT)
        self.modal_text_input.panel_content.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.modal_text_input.panel_content.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        label_title = lvr.title(self.modal_text_input.panel_content)
        label_title.set_text(title)
        label_title.set_style_margin_bottom(lv.dpx(10), lv.STATE.DEFAULT)

        textarea = lv.textarea(self.modal_text_input.panel_content)
        textarea.set_text(str(initial_value) if initial_value else "")
        textarea.set_one_line(True)
        textarea.set_width(lv.pct(95))
        textarea.set_style_text_font(lvr.get_font_text(), lv.STATE.DEFAULT)
        # Add basic style to textarea to match the theme
        textarea.set_style_bg_color(lv.color_lighten(lvr.COLOR_BACKGROUND, 16), lv.STATE.DEFAULT)
        textarea.set_style_text_color(lvr.COLOR_TEXT, lv.STATE.DEFAULT)
        textarea.set_style_border_width(1, lv.STATE.DEFAULT)
        textarea.set_style_border_color(lv.color_lighten(lvr.COLOR_BACKGROUND, 48), lv.STATE.DEFAULT)
        
        keyboard = lv.keyboard(self.modal_text_input.panel_content)
        keyboard.set_textarea(textarea)
        if is_number:
            try:
                keyboard.set_mode(lv.keyboard.MODE.NUMBER)
            except AttributeError:
                try:
                    keyboard.set_mode(lv.KEYBOARD_MODE.NUMBER)
                except AttributeError:
                    pass
        
        # Flex layout ignores absolute align, so we don't use set_align() here.
        # Instead, we just set the desired size and flex handles placement.
        keyboard.set_size(lv.pct(100), lv.pct(55))

        # Add flags to ensure the modal can receive touches and won't assert
        keyboard.add_flag(lv.OBJ_FLAG.CLICKABLE)

        # Style keyboard to match dark theme better
        keyboard.set_style_bg_color(lv.color_darken(lvr.COLOR_BACKGROUND, 16), lv.STATE.DEFAULT)
        # Handle different LVGL part constants across versions
        part_items = getattr(lv.PART, 'ITEMS', 0x00030000)
        state_default = getattr(lv.STATE.DEFAULT, 'value', int(lv.STATE.DEFAULT)) if hasattr(lv.STATE, 'DEFAULT') else 0
        keyboard.set_style_bg_color(lvr.COLOR_BACKGROUND, part_items | state_default)
        keyboard.set_style_text_color(lvr.COLOR_TEXT, part_items | state_default)

        def keyboard_event_cb(e):
            code = e.get_code()
            if code == lv.EVENT_CODE.READY or code == lv.EVENT_CODE.CANCEL:
                self.hide_modal()
                if code == lv.EVENT_CODE.READY and select_callback:
                    select_callback(textarea.get_text())

        keyboard.add_event_cb(keyboard_event_cb, lv.EVENT_CODE.READY, None)
        keyboard.add_event_cb(keyboard_event_cb, lv.EVENT_CODE.CANCEL, None)

        self.root_modal.clear_event_cb()
        self.root_modal.add_event_cb(lambda e: self.hide_modal(), lv.EVENT_CODE.CLICKED, None)
        
        self.show_modal(self.modal_text_input)

    def show_selection_dialog(self, options, select_callback=None):
        if self.modal_selection.panel_selection:
            self.modal_selection.panel_selection.delete()

        self.modal_selection.panel_selection = lvr.panel(self.modal_selection)
        self.modal_selection.panel_selection.set_style_pad_all(0, lv.STATE.DEFAULT)
        self.modal_selection.panel_selection.set_size(lv.pct(100), lv.SIZE_CONTENT)
        self.modal_selection.panel_selection.set_flex_flow(lv.FLEX_FLOW.ROW_WRAP)
        self.modal_selection.panel_selection.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        label_title = lvr.title(self.modal_selection.panel_selection)
        label_title.set_text('Select an option')
        label_title.set_align(lv.ALIGN.TOP_MID)
        label_title.set_style_margin_bottom(lvr.get_global_margin(), lv.STATE.DEFAULT)

        panel_options = lvr.panel(self.modal_selection.panel_selection)
        panel_options.set_style_pad_all(0, lv.STATE.DEFAULT)
        panel_options.set_size(lv.pct(100), lv.SIZE_CONTENT)
        panel_options.set_style_max_height(lv.dpx(300), lv.STATE.DEFAULT)
        panel_options.set_flex_flow(lv.FLEX_FLOW.ROW_WRAP)
        panel_options.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        for option in options:
            def select_option_cb(e, option=option):
                self.hide_modal()
                if select_callback:
                    select_callback(option)

            button_option = lvr.button(panel_options)
            button_option.set_text(option)
            button_option.add_event_cb(select_option_cb, lv.EVENT_CODE.CLICKED, None)

        self.root_modal.add_event_cb(lambda e: self.hide_modal(), lv.EVENT_CODE.CLICKED, None)
        self.show_modal(self.modal_selection)
    def show_fireworks(self):
        import random

        layer_top = lv.display_get_default().get_layer_top()
        layer_top.remove_flag(lv.OBJ_FLAG.SCROLLABLE)

        panel_fireworks = lvr.panel(layer_top)
        panel_fireworks.remove_flag(lv.OBJ_FLAG.SCROLLABLE)

        self.fireworks_hidden = False

        rocket_margin = lv.dpx(30)

        class Rocket:
            object = None
            color = None
            animation = None
            target = None
            stars = None
        class Star:
            animation = None
            object = None
            position = None
            velocity = None

        def make_star(rocket):
            star = Star()

            star.object = lv.obj(panel_fireworks)
            star.object.set_size(lv.dpx(8), lv.dpx(8))
            star.object.set_style_radius(lv.dpx(3), lv.STATE.DEFAULT)
            star.object.set_style_bg_color(rocket.color, lv.STATE.DEFAULT)
            star.object.set_style_border_opa(lv.OPA.TRANSP, lv.STATE.DEFAULT)
            star.object.set_pos(int(rocket.target[0]), int(rocket.target[1]))

            star.position = [rocket.target[0], rocket.target[1]]
            star.velocity = [(random.random() - 0.5) * 3, random.random() * 3]
            
            def star_animation_cb(o, value, star=star):
                star.velocity[1] -= 0.05
                star.position[0] = star.position[0] + star.velocity[0]
                star.position[1] = star.position[1] - star.velocity[1]
                star.object.set_pos(int(star.position[0]), int(star.position[1]))
                star.object.set_style_bg_opa(255 - value * 2, lv.STATE.DEFAULT)

            def star_completed_cb(e, star=star):
                star.animation.delete(None)
                star.object.delete()
            
            star.animation = lv.anim()
            star.animation.set_exec_cb(star_animation_cb)
            star.animation.set_completed_cb(star_completed_cb)
            star.animation.set_duration(1500)
            star.animation.set_values(0, 100)
            star.animation.start()
        def make_rocket():
            rocket = Rocket()

            rocket.color = lv.color_make(random.randint(64, 255), random.randint(64, 255), random.randint(64, 255))
            rocket.target = [random.randint(rocket_margin, self.screen_info.width - rocket_margin), random.randint(rocket_margin, self.screen_info.height / 2)]

            rocket.object = lv.obj(panel_fireworks)
            rocket.object.set_size(lv.dpx(6), lv.dpx(6))
            rocket.object.set_style_radius(lv.dpx(3), lv.STATE.DEFAULT)
            rocket.object.set_style_bg_color(rocket.color, lv.STATE.DEFAULT)
            rocket.object.set_style_border_opa(lv.OPA.TRANSP, lv.STATE.DEFAULT)

            def rocket_animation_cb(o, value, rocket=rocket):
                x = self.screen_info.width / 2 + (rocket.target[0] - self.screen_info.width / 2) * value / 100
                y = self.screen_info.height - (self.screen_info.height - rocket.target[1]) * value / 100
                rocket.object.set_pos(int(x), int(y))

            def rocket_completed_cb(e, rocket=rocket):
                if self.fireworks_hidden:
                    return
                rocket.stars = [ make_star(rocket) for i in range(8) ]
                rocket.target = [random.randint(rocket_margin, self.screen_info.width - rocket_margin), random.randint(rocket_margin, self.screen_info.height / 2)]
                rocket.color = lv.color_make(random.randint(64, 255), random.randint(64, 255), random.randint(64, 255))
                rocket.object.set_style_bg_color(rocket.color, lv.STATE.DEFAULT)
                rocket.animation.start()

            rocket.animation = lv.anim()
            rocket.animation.set_exec_cb(rocket_animation_cb)
            rocket.animation.set_completed_cb(rocket_completed_cb)
            rocket.animation.set_delay(random.randint(0, 2000))
            rocket.animation.set_duration(random.randint(1200, 2400))
            rocket.animation.set_values(0, 100)
            rocket.animation.set_path_cb(lv.anim_path_ease_out)
            rocket.animation.start()

        rockets = [ make_rocket() for i in range(6) ]

        colors = [
            lvr.COLOR_BACKGROUND,
            lv.color_mix(lvr.COLOR_BACKGROUND, lvr.COLOR_PRIMARY, 224)
        ]
        opas = [
            lv.OPA.TRANSP.value,
            lv.OPA.COVER.value
        ]
        fracs = [
            0,
            48
        ]

        grad_dsc = lv.grad_dsc()
        grad_dsc.init_stops(colors, opas, fracs, len(colors))
        grad_dsc.vertical_init()

        panel_message = lvr.panel(layer_top, lv.FLEX_FLOW.COLUMN)
        panel_message.set_flex_align(lv.FLEX_ALIGN.END, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        panel_message.set_size(lv.pct(100), lv.dpx(300))
        panel_message.set_align(lv.ALIGN.BOTTOM_MID)
        panel_message.remove_flag(lv.OBJ_FLAG.SCROLLABLE)
        panel_message.set_style_bg_grad(grad_dsc, lv.STATE.DEFAULT)
        panel_message.set_style_bg_opa(lv.OPA.COVER, lv.STATE.DEFAULT)

        label_text = lvr.label(panel_message)
        label_text.set_text('\n\nRinkhals has now reached 1000 community members and 256 GitHub stars.\nThank you for your interest in this project!\nHave fun priting :) Julien\n')
        label_text.set_width(lv.pct(100))
        label_text.set_style_text_font(lvr.get_font_subtitle(), lv.STATE.DEFAULT)
        label_text.set_long_mode(lv.LABEL_LONG_MODE.WRAP)
        label_text.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.STATE.DEFAULT)

        def close_fireworks(e, panel_fireworks=panel_fireworks, panel_message=panel_message):
            self.fireworks_hidden = True
            panel_fireworks.add_flag(lv.OBJ_FLAG.HIDDEN)
            panel_message.delete()

        button_close = lvr.button(panel_message)
        button_close.set_text('Yay! Let me print now!')
        button_close.add_event_cb(close_fireworks, lv.EVENT_CODE.CLICKED, None)
        button_close.set_style_margin_bottom(lv.dpx(15), lv.STATE.DEFAULT)

    def enable_app(self, app):
        logging.info(f'Enabling {app}...')
        enable_app(app)
        self.show_app(app)
    def disable_app(self, app):
        logging.info(f'Disabling {app}...')
        disable_app(app)
        self.show_app(app)
    def start_app(self, app):
        logging.info(f'Starting {app}...')
        start_app(app, 5)
        self.show_app(app)
    def stop_app(self, app):
        logging.info(f'Stopping {app}...')
        stop_app(app)
        self.show_app(app)

    def reboot_printer(self, e=None):
        logging.info('Rebooting printer...')

        if not USING_SIMULATOR:
            self.clear()
            system('sync && reboot')

        self.quit()
    def restart_rinkhals(self, e=None):
        logging.info('Restarting Boomslang...')

        if not USING_SIMULATOR:
            self.clear()
            system(RINKHALS_ROOT + '/start.sh')

        self.quit()
    def stop_rinkhals(self, e=None):
        logging.info('Stopping Boomslang...')

        if not USING_SIMULATOR:
            self.clear()
            system(RINKHALS_ROOT + '/stop.sh')

        self.quit()
    def disable_rinkhals(self, e=None):
        logging.info('Disabling Boomslang...')

        if not USING_SIMULATOR:
            self.clear()
            with open('/useremain/rinkhals/.disable-rinkhals', 'wb'):
                pass
            system('sync && reboot')

        self.quit()

    def clear(self):
        if not USING_SIMULATOR:
            system(f'dd if=/dev/zero of=/dev/fb0 bs={self.screen_info.width * 4} count={self.screen_info.height}')

    # Info dialog (home screen and Settings)
    def show_info_dialog(self):
        ip = printer_ip() or 'not connected'
        disk = '?'
        if USING_SHELL:
            disk = shell(f'df -Ph {RINKHALS_ROOT} | tail -n 1 | awk \'{{print $3 " / " $2 " (" $5 ")"}}\'') or '?'
        self.show_text_dialog(
            f'Boomslang {display_version(RINKHALS_VERSION)}\n{KOBRA_MODEL}\nFirmware {KOBRA_VERSION}\n\nAddress: {ip}\n'
            f'Web portal: port 8090\nMainsail: port 4409\nDisk usage: {disk}')

    # Home screen background work: the message after an automatic update, the
    # "update available" mark on the Updates card, and the live status line.
    WEB_APP = '65-rinkhals-web'       # its properties hold the updater and notification settings
    HOME_STATUS_SECONDS = 4

    def home_start_background(self):
        if USING_SIMULATOR:
            return
        notice = home_tools.take_update_notice(RINKHALS_VERSION)
        if notice:
            with lvr.lock():
                self.show_text_dialog(notice)
        run_async(self.home_check_update)
        import threading
        threading.Thread(target=self.home_status_loop, daemon=True).start()
        if self.home_theme != 'classic':
            threading.Thread(target=self.home_clock_loop, daemon=True).start()

    def home_check_update(self):
        try:
            # The installed version's channel: an Alpha is told about the next Alpha
            latest = Rinkhals.get_latest_version(channel=channel_of(RINKHALS_VERSION))
            if not (latest and latest.url and is_newer_release(latest.version, RINKHALS_VERSION)):
                return
            self.cache_rinkhals_latest = latest      # the Updates screen need not ask again
            with lvr.lock():
                self.home_show_update(latest)
        except Exception:
            logging.exception('Update check failed')

    def home_status_loop(self):
        shown = None
        while True:
            # Only while the home screen is what is on the display. LVGL is
            # not thread-safe, so the screen is looked at under its lock.
            with lvr.lock():
                on_home = (self.screen_current in (self.screen_main, self.screen_composition) and
                           self.root_modal.has_flag(lv.OBJ_FLAG.HIDDEN))
            if on_home:
                text = home_tools.fetch_status()
                if text != shown:
                    shown = text
                    with lvr.lock():
                        self.home_label_status.set_text(text)
            time.sleep(self.HOME_STATUS_SECONDS)

    # Phone notifications (Settings). The web portal sends them (notify.go);
    # here the topic is made and shown as a QR code for the ntfy app.
    def notifications_refresh(self):
        on = home_tools.valid_ntfy_topic(get_app_property(self.WEB_APP, 'ntfy_topic'))
        self.button_notifications.set_text(f'Phone notifications: {"on" if on else "off"}')

    def notifications_show_qr(self, topic):
        link = home_tools.ntfy_link(get_app_property(self.WEB_APP, 'ntfy_server'), topic)
        self.show_qr_dialog(link, 'Scan with the ntfy app to be\ntold when a print finishes,\nfails or pauses')

    def notifications_tap(self):
        topic = get_app_property(self.WEB_APP, 'ntfy_topic')
        if not home_tools.valid_ntfy_topic(topic):
            def turn_on():
                topic = home_tools.new_ntfy_topic()
                set_app_property(self.WEB_APP, 'ntfy_topic', topic)
                self.notifications_refresh()
                self.notifications_show_qr(topic)
            self.show_text_dialog('Phone notifications\n\nThe printer will send the\nfile name and what happened\n'
                                  'to ntfy.sh, a public service,\nunder a random secret topic.\n\nTurn them on?',
                                  action='Turn on', callback=turn_on)
            return

        def chosen(option):
            if option == 'Turn off':
                remove_app_property(self.WEB_APP, 'ntfy_topic')
                self.notifications_refresh()
            else:
                self.notifications_show_qr(topic)
        self.show_selection_dialog(['Show QR code', 'Turn off'], chosen)

    # Go back to the version that was installed before this one (Settings)
    def previous_version_tap(self):
        current_folder = ''
        try:
            with open(os.path.join(RINKHALS_BASE, '.version'), 'r') as f:
                current_folder = f.read().strip()
        except OSError:
            pass
        previous = home_tools.previous_install(RINKHALS_BASE, current_folder)
        if not previous:
            self.show_text_dialog('No previous version\nis installed.')
            return
        folder, version = previous

        def go_back():
            try:
                home_tools.select_install(RINKHALS_BASE, folder)
                # or the automatic updater would put this version straight back
                home_tools.keep_from_auto_install(RINKHALS_VERSION)
            except (OSError, ValueError) as e:
                logging.error(f'Could not go back to {folder}: {e}')
                self.show_text_dialog('Could not switch versions.\nNothing was changed.')
                return
            self.reboot_printer()
        self.show_text_dialog(f'Go back to\n{display_version(version)}?\n\nThe printer reboots.\n'
                              f'{display_version(RINKHALS_VERSION)}\nstays installed and will not\nbe installed again automatically.\n\n'
                              'Not during a print.', action='Go back', callback=go_back)

    # Switch to the original Rinkhals (Settings > Switch to Rinkhals).
    # Five deliberate steps before anything changes: two warning dialogs,
    # typing RINKHALS, a dialog with the release and a firmware check, and
    # the Download / Switch buttons of the install dialog. Nothing is written
    # until that last tap; the install itself is the normal OTA install of
    # the Rinkhals update package.
    SWITCH_CONFIRM_WORD = 'RINKHALS'
    switch_search = 0

    def switch_to_rinkhals_start(self):
        self.show_text_dialog(
            'WARNING\n'
            'Switch to Rinkhals?\n\n'
            'This removes Boomslang and\n'
            'installs the original Rinkhals\n'
            '(rinkhals-community on GitHub).\n\n'
            'You lose the Boomslang home\n'
            'screen, the browser, automatic\n'
            'updates, the Boomslang app\n'
            'store and the support for\n'
            'newer firmware Boomslang adds.',
            action='I understand', action_color=lvr.COLOR_DANGER,
            callback=self.switch_to_rinkhals_second)

    def switch_to_rinkhals_second(self):
        self.show_text_dialog(
            'ARE YOU SURE?\n\n'
            'Rinkhals may not support\n'
            f'firmware {KOBRA_VERSION}. If it does not,\n'
            'the printer starts with the\n'
            'stock Anycubic software only.\n\n'
            'There is no button to come back.\n'
            'To return, install a Boomslang\n'
            'update.swu from a USB drive.\n\n'
            'Never do this during a print.',
            action='Continue', action_color=lvr.COLOR_DANGER,
            callback=lambda: self.show_input_text_dialog(
                f'Type {self.SWITCH_CONFIRM_WORD} to confirm', '', False, self.switch_to_rinkhals_typed))

    def switch_to_rinkhals_typed(self, text):
        if (text or '').strip().upper() != self.SWITCH_CONFIRM_WORD:
            self.show_text_dialog('Not confirmed.\nBoomslang was not changed.')
            return

        self.switch_search += 1
        search = self.switch_search
        self.show_text_dialog('Looking for the latest\nRinkhals release...', action='Cancel',
                              callback=lambda: setattr(self, 'switch_search', self.switch_search + 1))

        def find_release():
            versions = Rinkhals.get_available_versions(include_test=False, limit=1,
                                                       repo=RINKHALS_REPO, compressed=False)
            with lvr.lock():
                # Cancelled, or the dialog was tapped away while GitHub answered
                if search != self.switch_search or self.root_modal.has_flag(lv.OBJ_FLAG.HIDDEN):
                    return
                if not versions:
                    self.show_text_dialog('No Rinkhals release for this\nprinter was found, or GitHub\n'
                                          'could not be reached.\n\nBoomslang was not changed.')
                    return
                version = versions[0]
                version.switch_warning = switch_warning_text(version.version, version.changes, KOBRA_VERSION)
                self.show_ota_rinkhals_modal(version)
        run_async(find_release)

    # Web browser (reader mode: text, headings and links, no JavaScript)
    BROWSER_NAME = 'LemSearch Lite'
    BROWSER_BOOKMARKS = [
        ('Wikipedia', 'https://en.m.wikipedia.org/wiki/Main_Page'),
        ('Hacker News', 'https://news.ycombinator.com'),
        ('Klipper documentation', 'https://www.klipper3d.org/'),
        ('Boomslang on GitHub', 'https://github.com/Gubir34/Boomslang'),
        ('Printables search', 'https://html.duckduckgo.com/html/?q=printables+3d+models'),
    ]
    BROWSER_BLOCKS_PER_STEP = 20     # widgets created per lock hold, so the screen keeps responding
    BROWSER_BLOCKS_PER_PART = 300    # a long page is shown in parts: widgets are what costs memory
    BROWSER_MAX_LINK_BUTTONS = 100   # each button costs memory on a printer with little of it

    screen_browser = None
    browser_history = None
    browser_url = None            # last page that loaded
    browser_showing_url = False   # whether that page is what is on screen
    browser_page = None           # the page on screen, for moving between its parts
    browser_gen = 0   # bumped by every navigation; a slow page that is no longer wanted is dropped

    def layout_browser(self):
        self.browser_history = []
        self.screen_browser = lvr.panel(self.root_screen, tag='screen_browser')
        if self.screen_browser:
            self.screen_browser.add_flag(lv.OBJ_FLAG.HIDDEN)
            self.screen_browser.set_size(lv.pct(100), lv.pct(100))
            self.screen_browser.set_style_pad_all(0, lv.STATE.DEFAULT)
            self.screen_browser.set_style_pad_top(lvr.get_title_bar_height(), lv.STATE.DEFAULT)

            title_bar = lvr.title_bar(self.screen_browser)
            title_bar.set_y(-lvr.get_title_bar_height())

            self.screen_browser.label_title = lvr.title(title_bar)
            self.screen_browser.label_title.set_text(self.BROWSER_NAME)
            self.screen_browser.label_title.center()

            icon_back = lvr.button_icon(title_bar)
            icon_back.set_align(lv.ALIGN.LEFT_MID)
            icon_back.set_text('\ue314')
            icon_back.add_event_cb(lambda e: self.browser_back(), lv.EVENT_CODE.CLICKED, None)

            icon_go = lvr.button_icon(title_bar)
            icon_go.set_align(lv.ALIGN.RIGHT_MID)
            icon_go.set_text('\ue8b6')
            icon_go.add_event_cb(lambda e: self.browser_ask_address(), lv.EVENT_CODE.CLICKED, None)

            self.screen_browser.panel_content = None

    def browser_show(self):
        if not self.screen_browser:
            self.show_screen(None)
            return
        self.show_screen(self.screen_browser)
        if not self.screen_browser.panel_content:
            self.browser_start_page()

    def browser_new_content(self):
        if self.screen_browser.panel_content:
            self.screen_browser.panel_content.delete()
        panel = lvr.panel(self.screen_browser, flex_flow=lv.FLEX_FLOW.COLUMN)
        panel.set_size(lv.pct(100), lv.pct(100))
        self.screen_browser.panel_content = panel
        return panel

    def browser_ask_address(self):
        self.show_input_text_dialog('Address or search', self.browser_url or '', False,
                                    lambda text: self.browser_open(text))

    def browser_back(self):
        self.browser_gen += 1
        if self.browser_url and not self.browser_showing_url:
            # A link is still loading or failed: go back to the page it was
            # opened from, which browser_url still names
            self.browser_open(self.browser_url, push=False)
        elif self.browser_history:
            self.browser_open(self.browser_history.pop(), push=False)
        elif self.browser_url:
            self.browser_url = None
            self.browser_start_page()
        else:
            self.show_screen(self.screen_main)

    def browser_label(self, parent, text, kind='p', color=None, align=None, decor=None, bg=None, big=False):
        if kind == 'h1' or big:
            label = lvr.title(parent)
        else:
            label = lvr.label(parent)
            if kind in ('h2', 'h3'):
                label.set_style_text_color(lvr.COLOR_PRIMARY, lv.STATE.DEFAULT)
            elif kind in ('quote', 'pre'):
                label.set_style_text_color(lvr.COLOR_SUBTITLE, lv.STATE.DEFAULT)
        # Colour and alignment from the page's own CSS (reader.py already
        # dropped colours that would be unreadable on the dark screen)
        if bg:
            # A highlighted box (a notice, a marked passage): the page's own
            # background, with black or white text, whichever reads on it
            label.set_style_bg_color(lv.color_make(*bg), lv.STATE.DEFAULT)
            label.set_style_bg_opa(lv.OPA.COVER, lv.STATE.DEFAULT)
            label.set_style_pad_all(lv.dpx(6), lv.STATE.DEFAULT)
            label.set_style_radius(lv.dpx(6), lv.STATE.DEFAULT)
            color = (0, 0, 0) if (0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2]) / 255 > 0.5 else (255, 255, 255)
        if color:
            label.set_style_text_color(lv.color_make(*color), lv.STATE.DEFAULT)
        if decor == 'strike':
            label.set_style_text_decor(lv.TEXT_DECOR.STRIKETHROUGH, lv.STATE.DEFAULT)
        elif decor == 'underline':
            label.set_style_text_decor(lv.TEXT_DECOR.UNDERLINE, lv.STATE.DEFAULT)
        if align == 'center':
            label.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.STATE.DEFAULT)
        elif align == 'right':
            label.set_style_text_align(lv.TEXT_ALIGN.RIGHT, lv.STATE.DEFAULT)
        label.set_width(lv.pct(100))
        label.set_long_mode(lv.LABEL_LONG_MODE.WRAP)
        label.set_text(('\u2022 ' + text) if kind == 'li' else text)
        return label

    def browser_link(self, parent, text, url):
        button = lvr.button(parent)
        button.set_width(lv.pct(100))
        button.set_text(ellipsis(text, 40))
        button.set_style_pad_left(lv.dpx(15), lv.STATE.DEFAULT)
        button.set_style_text_align(lv.TEXT_ALIGN.LEFT, lv.STATE.DEFAULT)
        button.set_style_text_color(lvr.COLOR_PRIMARY, lv.STATE.DEFAULT)
        if url:
            button.add_event_cb(lambda e, u=url: self.browser_open(u), lv.EVENT_CODE.CLICKED, None)
        return button

    def browser_search_field(self, parent, text=None):
        """The search box at the top: tap to type words or an address."""
        field = lvr.button(parent)
        field.set_width(lv.pct(100))
        field.set_icon('\ue8b6')
        field.set_text(ellipsis(text, 40) if text else 'Search the web or type an address')
        field.set_flex_flow(lv.FLEX_FLOW.ROW)
        field.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        # lvr.button makes its icon and text 100 % wide (it lays them out in a
        # column); side by side the icon took the whole row and hid the text
        icon, words = field.get_child(0), field.get_child(1)
        icon.set_width(lv.SIZE_CONTENT)
        words.set_width(1)
        words.set_flex_grow(1)
        words.set_long_mode(lv.LABEL_LONG_MODE.DOTS)
        words.set_style_text_align(lv.TEXT_ALIGN.LEFT, lv.STATE.DEFAULT)
        field.set_style_pad_column(lv.dpx(12), lv.STATE.DEFAULT)
        field.set_style_pad_left(lv.dpx(18), lv.STATE.DEFAULT)
        field.set_style_text_color(lvr.COLOR_TEXT if text else lvr.COLOR_SUBTITLE, lv.STATE.DEFAULT)
        field.add_event_cb(lambda e: self.show_input_text_dialog('Search or address', text or '', False,
                                                                 lambda typed: self.browser_open(typed)),
                           lv.EVENT_CODE.CLICKED, None)
        return field

    def browser_start_page(self):
        self.browser_gen += 1
        self.browser_showing_url = False
        self.screen_browser.label_title.set_text(self.BROWSER_NAME)
        panel = self.browser_new_content()
        self.browser_search_field(panel)
        self.browser_label(panel, 'Pages are shown as text with links. Sites that need a full browser '
                                  'can be opened on your phone with a QR code.', 'quote')
        saved = home_tools.load_bookmarks()
        for name, url in saved:
            self.browser_link(panel, name, url)
        for name, url in self.BROWSER_BOOKMARKS:
            if not any(url == u for _, u in saved):
                self.browser_link(panel, name, url)

    def browser_phone_link(self, panel, url):
        """Offer to carry on on the phone: a QR code of the address."""
        self.browser_link(panel, 'Open on your phone', None).add_event_cb(
            lambda e, u=url: self.show_qr_dialog(u, 'Scan to open this page\non your phone'), lv.EVENT_CODE.CLICKED, None)

    def browser_result_card(self, panel, result):
        """A search result as in the LemSearch mockup: the site, the title in green, a few words."""
        card = lvr.button(panel)
        card.set_width(lv.pct(100))
        card.set_height(lv.SIZE_CONTENT)
        card.set_style_min_height(0, lv.STATE.DEFAULT)
        card.set_style_pad_all(lv.dpx(12), lv.STATE.DEFAULT)
        card.set_style_pad_row(lv.dpx(3), lv.STATE.DEFAULT)
        card.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START)
        card.set_style_text_align(lv.TEXT_ALIGN.LEFT, lv.STATE.DEFAULT)   # buttons centre their text
        card.set_style_radius(lv.dpx(16), lv.STATE.DEFAULT)              # not a capsule: cards are tall
        site = lvr.subtitle(card)
        site.set_text(ellipsis(result['domain'], 48))
        title = lvr.label(card)
        title.set_width(lv.pct(100))
        title.set_long_mode(lv.LABEL_LONG_MODE.WRAP)
        title.set_style_text_color(lvr.COLOR_PRIMARY, lv.STATE.DEFAULT)
        title.set_text(ellipsis(result['title'], 90))
        if result['snippet']:
            words = lvr.subtitle(card)
            words.set_width(lv.pct(100))
            words.set_long_mode(lv.LABEL_LONG_MODE.WRAP)
            words.set_text(ellipsis(result['snippet'], 160))
        card.add_event_cb(lambda e, u=result['url']: self.browser_open(u), lv.EVENT_CODE.CLICKED, None)
        return card

    def browser_render_results(self, results, error, url, push, gen):
        query = reader.search_query(url)
        with lvr.lock():
            if gen != self.browser_gen:
                return
            panel = self.browser_new_content()
            self.browser_search_field(panel, query)
            if error:
                self.screen_browser.label_title.set_text('Cannot search')
                self.browser_label(panel, error, 'p')
                self.browser_link(panel, 'Try again', None).add_event_cb(
                    lambda e, u=url, p=push: self.browser_open(u, push=p), lv.EVENT_CODE.CLICKED, None)
                return
            if push and self.browser_url:
                self.browser_history.append(self.browser_url)
                del self.browser_history[:-30]
            self.browser_url = url
            self.browser_page = None
            self.browser_showing_url = True
            self.screen_browser.label_title.set_text(self.BROWSER_NAME)
            if not results:
                self.browser_label(panel, 'Nothing found. Try other words.', 'quote')
        for i in range(0, len(results), 5):
            with lvr.lock():
                if gen != self.browser_gen:
                    return
                for result in results[i:i + 5]:
                    self.browser_result_card(panel, result)

    def browser_form(self, form, label):
        self.show_input_text_dialog(label, '', False,
                                    lambda text: self.browser_open(reader.submit_url(form, text)) if text else None)

    def browser_bookmark_text(self, url):
        return 'Remove bookmark' if home_tools.is_bookmarked(url) else 'Bookmark this page'

    def browser_show_part(self, start):
        page = self.browser_page
        if not page:
            return
        self.browser_gen += 1
        gen = self.browser_gen
        run_async(lambda: self.browser_render(page, None, page.url, False, gen, start))

    def browser_open(self, target, push=True):
        if not target:
            return
        try:
            url = reader.normalize_url(target)
        except reader.BrowserError as e:
            self.show_text_dialog(str(e))
            return
        self.browser_gen += 1
        gen = self.browser_gen
        self.browser_showing_url = False
        self.screen_browser.label_title.set_text('Loading...')
        panel = self.browser_new_content()
        self.browser_label(panel, ellipsis(url, 90), 'quote')

        def load():
            page, error = None, None
            if reader.is_search(url):
                results = []
                try:
                    results = reader.search(url)
                except reader.BrowserError as e:
                    error = str(e)
                except Exception as e:
                    logging.exception('Search failed')
                    error = f'Unexpected error: {type(e).__name__}'
                self.browser_render_results(results, error, url, push, gen)
                return
            try:
                page = reader.fetch(url)
            except reader.BlockedError as e:
                error = (str(e), True)
            except reader.BrowserError as e:
                error = str(e)
            except Exception as e:
                logging.exception('Browser failed')
                error = f'Unexpected error: {type(e).__name__}'
            self.browser_render(page, error, url, push, gen)
        run_async(load)

    def browser_render(self, page, error, url, push, gen, start=0):
        # Every "is this page still wanted" check is made while holding the
        # LVGL lock. Taps run inside lv.timer_handler(), which holds the same
        # lock, so a navigation can't delete the panel between the check and
        # the widgets being added to it.
        with lvr.lock():
            if gen != self.browser_gen:
                return  # the user went somewhere else while it loaded
            panel = self.browser_new_content()
            if error:
                blocked = isinstance(error, tuple)
                message = error[0] if blocked else error
                self.screen_browser.label_title.set_text('Needs a full browser' if blocked else 'Cannot open page')
                self.browser_label(panel, message, 'p')
                self.browser_label(panel, ellipsis(url, 90), 'quote')
                if blocked:
                    self.browser_phone_link(panel, url)
                self.browser_link(panel, 'Try again', None).add_event_cb(
                    lambda e, u=url, p=push: self.browser_open(u, push=p), lv.EVENT_CODE.CLICKED, None)
                return
            if push and self.browser_url:
                self.browser_history.append(self.browser_url)
                del self.browser_history[:-30]
            self.browser_url = page.url
            self.browser_page = page
            self.browser_showing_url = True
            self.screen_browser.label_title.set_text(ellipsis(page.title, 24))

            # A long page is shown in parts; each part is its own set of widgets
            per_part = self.BROWSER_BLOCKS_PER_PART
            parts = max(1, -(-len(page.blocks) // per_part))
            part = start // per_part + 1
            if start > 0:
                self.browser_link(panel, f'Previous part ({part - 1} of {parts})', None).add_event_cb(
                    lambda e, s=start - per_part: self.browser_show_part(max(0, s)), lv.EVENT_CODE.CLICKED, None)
            elif getattr(page, 'from_data', False):
                self.browser_label(panel, 'This page is drawn by JavaScript, which is not run here. '
                                          'Below is the text found in the data it carries.', 'quote')
                self.browser_phone_link(panel, page.url)
            elif getattr(page, 'from_summary', False):
                self.browser_label(panel, 'This page is drawn by JavaScript, which is not run here. '
                                          'Below is the summary it gives for link previews.', 'quote')
                self.browser_phone_link(panel, page.url)

        blocks = page.blocks[start:start + per_part]
        links_left = self.BROWSER_MAX_LINK_BUTTONS
        hidden_links = 0
        step = self.BROWSER_BLOCKS_PER_STEP
        for i in range(0, len(blocks), step):
            with lvr.lock():
                if gen != self.browser_gen:
                    return
                for block in blocks[i:i + step]:
                    if block['kind'] == 'form':
                        label = block['text'] or 'Search'
                        caption = f'{label}...' if label.lower().startswith('search') else f'Search: {label}...'
                        self.browser_link(panel, caption, None).add_event_cb(
                            lambda e, f=block['form'], l=label: self.browser_form(f, l), lv.EVENT_CODE.CLICKED, None)
                        continue
                    if block['text']:
                        self.browser_label(panel, block['text'], block['kind'],
                                           block.get('color'), block.get('align'),
                                           block.get('decor'), block.get('bg'), block.get('big', False))
                    for text, link in block['links']:
                        if links_left > 0:
                            self.browser_link(panel, text, link)
                            links_left -= 1
                        else:
                            hidden_links += 1
        with lvr.lock():
            if gen != self.browser_gen:
                return
            notes = []
            last_part = start + per_part >= len(page.blocks)
            if hidden_links:
                notes.append(f'{hidden_links} more links are not shown.')
            if page.truncated and last_part:
                notes.append('The page is very long: the end of it is not shown.')
            if not page.blocks:
                notes.append('This page has no readable text. It probably needs a full browser.')
            for note in notes:
                self.browser_label(panel, note, 'quote')
            if not page.blocks:
                self.browser_phone_link(panel, page.url)
            if not last_part:
                self.browser_link(panel, f'Continue reading (part {part + 1} of {parts})', None).add_event_cb(
                    lambda e: self.browser_show_part(start + per_part), lv.EVENT_CODE.CLICKED, None)
            else:
                bookmark = self.browser_link(panel, self.browser_bookmark_text(page.url), None)

                def toggle(e):
                    home_tools.toggle_bookmark(page.title, page.url)
                    bookmark.set_text(self.browser_bookmark_text(page.url))
                bookmark.add_event_cb(toggle, lv.EVENT_CODE.CLICKED, None)

    # App Store
    APP_STORE_REPO = 'Gubir34/Boomslang.Apps'
    APP_STORE_BRANCH = 'master'

    screen_store = None
    screen_store_app = None
    modal_store_install = None

    def layout_app_store(self):
        # App Store listing screen
        self.screen_store = lvr.panel(self.root_screen, tag='screen_store')
        if self.screen_store:
            self.screen_store.add_flag(lv.OBJ_FLAG.HIDDEN)
            self.screen_store.set_size(lv.pct(100), lv.pct(100))
            self.screen_store.set_style_pad_all(0, lv.STATE.DEFAULT)
            self.screen_store.set_style_pad_top(lvr.get_title_bar_height(), lv.STATE.DEFAULT)

            title_bar = lvr.title_bar(self.screen_store)
            title_bar.set_y(-lvr.get_title_bar_height())

            title = lvr.title(title_bar)
            title.set_text('App Store')
            title.center()

            icon_back = lvr.button_icon(title_bar)
            icon_back.set_align(lv.ALIGN.LEFT_MID)
            icon_back.set_text('\ue314')
            icon_back.add_event_cb(lambda e: self.show_screen(self.screen_main), lv.EVENT_CODE.CLICKED, None)

            icon_refresh = lvr.button_icon(title_bar)
            icon_refresh.add_event_cb(lambda e: self.show_screen(self.screen_store), lv.EVENT_CODE.CLICKED, None)
            icon_refresh.set_align(lv.ALIGN.RIGHT_MID)
            icon_refresh.set_text('\ue5d5')

            self.screen_store.panel_apps = None

        # App Store app detail screen
        self.screen_store_app = lvr.panel(self.root_screen, tag='screen_store_app')
        if self.screen_store_app:
            self.screen_store_app.add_flag(lv.OBJ_FLAG.HIDDEN)
            self.screen_store_app.set_size(lv.pct(100), lv.pct(100))
            self.screen_store_app.set_style_pad_all(0, lv.STATE.DEFAULT)
            self.screen_store_app.set_style_pad_top(lvr.get_title_bar_height(), lv.STATE.DEFAULT)

            title_bar = lvr.title_bar(self.screen_store_app)
            title_bar.set_y(-lvr.get_title_bar_height())

            icon_back = lvr.button_icon(title_bar)
            icon_back.set_align(lv.ALIGN.LEFT_MID)
            icon_back.set_text('\ue314')
            icon_back.add_event_cb(lambda e: self.show_screen(self.screen_store), lv.EVENT_CODE.CLICKED, None)

            self.screen_store_app.label_title = lvr.title(title_bar)
            self.screen_store_app.label_title.center()

            panel_app = lvr.panel(self.screen_store_app, flex_flow=lv.FLEX_FLOW.COLUMN, flex_align=lv.FLEX_ALIGN.CENTER)
            panel_app.set_size(lv.pct(100), lv.pct(100))

            self.screen_store_app.label_version = lvr.subtitle(panel_app)
            self.screen_store_app.label_version.set_text('Version:')
            self.screen_store_app.label_version.set_style_margin_ver(-lvr.get_global_margin() - lv.dpx(2), lv.STATE.DEFAULT)

            self.screen_store_app.label_description = lvr.subtitle(panel_app)
            self.screen_store_app.label_description.set_style_text_color(lvr.COLOR_TEXT, lv.STATE.DEFAULT)
            self.screen_store_app.label_description.set_width(lv.pct(100))
            self.screen_store_app.label_description.set_long_mode(lv.LABEL_LONG_MODE.WRAP)
            self.screen_store_app.label_description.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.STATE.DEFAULT)

            self.screen_store_app.button_action = lvr.button(panel_app)
            self.screen_store_app.button_action.set_width(lv.pct(100))
            self.screen_store_app.button_action.set_text('Install')

        # Install progress modal
        self.modal_store_install = lvr.modal(self.root_modal, tag='modal_store_install')
        if self.modal_store_install:
            self.modal_store_install.set_flex_flow(lv.FLEX_FLOW.COLUMN)
            self.modal_store_install.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

            self.modal_store_install.label_title = lvr.title(self.modal_store_install)
            self.modal_store_install.label_title.set_width(lv.pct(100))
            self.modal_store_install.label_title.set_height(lvr.get_font_title().get_line_height())
            self.modal_store_install.label_title.set_style_pad_bottom(lvr.get_global_margin(), lv.STATE.DEFAULT)
            self.modal_store_install.label_title.set_long_mode(lv.LABEL_LONG_MODE.DOTS)
            self.modal_store_install.label_title.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.STATE.DEFAULT)

            panel_progress_background = lvr.panel(self.modal_store_install)
            panel_progress_background.set_size(lv.pct(100), lv.dpx(10))
            panel_progress_background.set_style_pad_all(0, lv.STATE.DEFAULT)
            panel_progress_background.set_style_bg_color(lv.color_lighten(lvr.COLOR_BACKGROUND, 48), lv.STATE.DEFAULT)
            panel_progress_background.set_style_bg_opa(lv.OPA.COVER, lv.STATE.DEFAULT)
            panel_progress_background.remove_flag(lv.OBJ_FLAG.SCROLLABLE)

            self.modal_store_install.obj_progress_bar = lvr.panel(panel_progress_background)
            self.modal_store_install.obj_progress_bar.set_align(lv.ALIGN.LEFT_MID)
            self.modal_store_install.obj_progress_bar.set_style_bg_color(lvr.COLOR_PRIMARY, lv.STATE.DEFAULT)
            self.modal_store_install.obj_progress_bar.set_style_bg_opa(lv.OPA.COVER, lv.STATE.DEFAULT)
            self.modal_store_install.obj_progress_bar.set_size(lv.pct(0), lv.pct(100))

            self.modal_store_install.label_progress_text = lvr.label(self.modal_store_install)
            self.modal_store_install.label_progress_text.set_text('')

            panel_actions = lvr.panel(self.modal_store_install)
            panel_actions.set_width(lv.pct(100))
            panel_actions.set_flex_flow(lv.FLEX_FLOW.ROW)
            panel_actions.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
            panel_actions.set_style_pad_column(lv.dpx(15), lv.STATE.DEFAULT)
            panel_actions.set_style_pad_all(0, lv.STATE.DEFAULT)
            panel_actions.set_style_pad_top(lvr.get_global_margin(), lv.STATE.DEFAULT)

            self.modal_store_install.button_cancel = lvr.button(panel_actions)
            self.modal_store_install.button_cancel.set_width(lv.pct(45))
            self.modal_store_install.button_cancel.set_text('Cancel')
            self.modal_store_install.button_cancel.add_event_cb(lambda e: self.hide_modal(), lv.EVENT_CODE.CLICKED, None)

            self.modal_store_install.button_done = lvr.button(panel_actions)
            self.modal_store_install.button_done.set_width(lv.pct(45))
            self.modal_store_install.button_done.set_text('Done')
            self.modal_store_install.button_done.add_flag(lv.OBJ_FLAG.HIDDEN)
            self.modal_store_install.button_done.add_event_cb(lambda e: self.hide_modal(), lv.EVENT_CODE.CLICKED, None)

    def fetch_store_manifest(self, app_dir, ref, api_headers):
        # Read the manifest at the release tag first so the version we show is
        # the one bundled in the installable SWU. Apps added after the release
        # won't exist at the tag, so fall back to the branch for display.
        import requests
        cache = self.__dict__.setdefault('store_manifest_cache', {})
        cached = cache.get((app_dir, ref))
        if cached and time.time() - cached[0] < 600:
            return cached[1]
        refs = [ref] + ([self.APP_STORE_BRANCH] if ref != self.APP_STORE_BRANCH else [])
        for r in refs:
            try:
                url = f'https://raw.githubusercontent.com/{self.APP_STORE_REPO}/{r}/apps/{app_dir}/app.json'
                resp = requests.get(url, headers=api_headers, timeout=5)
                if resp.status_code == 200:
                    manifest = json.loads(resp.text, cls=JSONWithCommentsDecoder)
                    cache[(app_dir, ref)] = (time.time(), manifest)
                    return manifest
            except Exception:
                pass
        return {}

    def installed_app_version(self, app_dir):
        # Returns (version, is_installed) for a locally installed app.
        path = f'{RINKHALS_HOME}/apps/{app_dir}/app.json'
        if not os.path.exists(path):
            return '', False
        try:
            with open(path) as f:
                return (json.load(f, cls=JSONWithCommentsDecoder).get('version') or ''), True
        except Exception:
            return '', True

    def show_app_store(self):
        if self.screen_store.panel_apps:
            self.screen_store.panel_apps.delete()
        self.screen_store.panel_apps = lvr.panel(self.screen_store, flex_flow=lv.FLEX_FLOW.COLUMN)
        self.screen_store.panel_apps.set_size(lv.pct(100), lv.pct(100))

        label_loading = lvr.subtitle(self.screen_store.panel_apps)
        label_loading.set_text('Loading...')
        label_loading.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.STATE.DEFAULT)
        label_loading.center()

        self.store_generation = getattr(self, 'store_generation', 0) + 1
        generation = self.store_generation
        panel_apps = self.screen_store.panel_apps

        # Leaving and opening the store again (or Refresh) deletes this panel and
        # its label while this load still runs. Touching them then crashed the
        # menu, so every change below first checks, under the lock, that this
        # load is still the current one.
        def current():
            return generation == self.store_generation

        def fetch_apps():
            try:
                import requests
                api_headers = {'User-Agent': 'Rinkhals-AppStore/1.0'}
                api_url = f'https://api.github.com/repos/{self.APP_STORE_REPO}/contents/apps'
                response = requests.get(api_url, headers=api_headers, timeout=10)
                if response.status_code != 200:
                    if response.status_code == 403 and response.headers.get('X-RateLimit-Remaining') == '0':
                        msg = 'Rate limit exceeded\nTry again in a few minutes'
                    else:
                        msg = f'Failed to load ({response.status_code})'
                    with lvr.lock():
                        if current():
                            label_loading.set_text(msg)
                    return

                entries = response.json()
                app_dirs = [e for e in entries if e.get('type') == 'dir']

                # Resolve the latest release tag and read manifests from it, so
                # the versions shown match the SWUs that will install (branch
                # HEAD can be ahead of the released build).
                manifest_ref = self.APP_STORE_BRANCH
                try:
                    rel_resp = requests.get(f'https://api.github.com/repos/{self.APP_STORE_REPO}/releases/latest', headers=api_headers, timeout=10)
                    if rel_resp.status_code == 200:
                        manifest_ref = rel_resp.json().get('tag_name') or self.APP_STORE_BRANCH
                except Exception:
                    pass

                # The manifests are small files on a slow link: read several at
                # once instead of one after the other (42 apps took minutes)
                from concurrent.futures import ThreadPoolExecutor
                app_names = [e.get('name') for e in app_dirs if e.get('name')]
                with ThreadPoolExecutor(max_workers=6) as pool:
                    manifests = list(pool.map(lambda d: self.fetch_store_manifest(d, manifest_ref, api_headers), app_names))
                with lvr.lock():
                    if not current():
                        return  # the user left the store and came back: this list is stale
                    label_loading.add_flag(lv.OBJ_FLAG.HIDDEN)

                for app_dir, app_manifest in zip(app_names, manifests):

                    app_name = app_manifest.get('name') or app_dir
                    app_version = app_manifest.get('version') or ''
                    installed_version, is_installed = self.installed_app_version(app_dir)
                    update_available = bool(is_installed and installed_version and app_version and installed_version != app_version)

                    with lvr.lock():
                        if not current():
                            return
                        panel_app = lvr.panel(panel_apps)
                        panel_app.set_size(lv.pct(100), lv.dpx(70))
                        panel_app.set_style_border_side(lv.BORDER_SIDE.BOTTOM, lv.STATE.DEFAULT)
                        panel_app.set_state(lv.STATE.DISABLED, False)
                        panel_app.add_event_cb(lambda e, d=app_dir, m=app_manifest: self.show_app_store_app(d, m), lv.EVENT_CODE.CLICKED, None)

                        label_name = lvr.label(panel_app)
                        label_name.set_align(lv.ALIGN.TOP_LEFT if app_version else lv.ALIGN.LEFT_MID)
                        label_name.set_text(app_name)

                        if app_version:
                            label_ver = lvr.subtitle(panel_app)
                            label_ver.set_align(lv.ALIGN.BOTTOM_LEFT)
                            label_ver.set_style_text_color(lvr.COLOR_DISABLED, lv.STATE.DEFAULT)
                            label_ver.set_text(f'v{app_version}')

                        if is_installed:
                            label_installed = lvr.subtitle(panel_app)
                            label_installed.set_align(lv.ALIGN.RIGHT_MID)
                            label_installed.set_style_text_color(lvr.COLOR_PRIMARY, lv.STATE.DEFAULT)
                            label_installed.set_text('Update' if update_available else 'Installed')

            except Exception as ex:
                logging.error(f'App store fetch failed: {ex}')
                with lvr.lock():
                    if current():
                        label_loading.set_text(f'Error loading apps')

        run_async(fetch_apps)

    def show_app_store_app(self, app_dir, app_manifest):
        self.show_screen(self.screen_store_app)

        app_name = app_manifest.get('name') or app_dir
        app_version = app_manifest.get('version') or ''
        app_description = app_manifest.get('description') or ''
        installed_version, is_installed = self.installed_app_version(app_dir)
        update_available = bool(is_installed and installed_version and app_version and installed_version != app_version)

        self.screen_store_app.label_title.set_text(ellipsis(app_name, 24))
        if update_available:
            self.screen_store_app.label_version.set_text(f'Version: {installed_version} -> {app_version}')
        else:
            self.screen_store_app.label_version.set_text(f'Version: {app_version}' if app_version else '')
        self.screen_store_app.label_description.set_text(app_description)

        self.screen_store_app.button_action.clear_event_cb()

        if update_available:
            # Single action button, so Update takes priority over Remove while an
            # update is pending. Reinstalling the SWU upgrades in place; the
            # button reverts to Remove once installed == available.
            self.screen_store_app.button_action.set_text('Update')
            self.screen_store_app.button_action.set_style_text_color(lvr.COLOR_PRIMARY, lv.STATE.DEFAULT)
            self.screen_store_app.button_action.add_event_cb(
                lambda e, d=app_dir, n=app_name: self.install_store_app(d, n),
                lv.EVENT_CODE.CLICKED, None
            )
        elif is_installed:
            self.screen_store_app.button_action.set_text('Remove')
            self.screen_store_app.button_action.set_style_text_color(lvr.COLOR_DANGER, lv.STATE.DEFAULT)
            self.screen_store_app.button_action.add_event_cb(
                lambda e, d=app_dir, n=app_name: self.show_text_dialog(
                    f'Remove {n}?\n\nThis will delete all app files.',
                    action='Remove',
                    action_color=lvr.COLOR_DANGER,
                    callback=lambda: self.remove_store_app(d)
                ),
                lv.EVENT_CODE.CLICKED, None
            )
        else:
            self.screen_store_app.button_action.set_text('Install')
            self.screen_store_app.button_action.set_style_text_color(lvr.COLOR_TEXT, lv.STATE.DEFAULT)
            self.screen_store_app.button_action.add_event_cb(
                lambda e, d=app_dir, n=app_name: self.install_store_app(d, n),
                lv.EVENT_CODE.CLICKED, None
            )

    def install_store_app(self, app_dir, app_name):
        with lvr.lock():
            self.modal_store_install.label_title.set_text(f'Installing {app_name}')
            self.modal_store_install.obj_progress_bar.set_width(lv.pct(0))
            self.modal_store_install.obj_progress_bar.set_style_bg_color(lvr.COLOR_PRIMARY, lv.STATE.DEFAULT)
            self.modal_store_install.label_progress_text.set_text('Starting...')
            self.modal_store_install.button_cancel.remove_flag(lv.OBJ_FLAG.HIDDEN)
            self.modal_store_install.button_done.add_flag(lv.OBJ_FLAG.HIDDEN)

        self.show_modal(self.modal_store_install)

        def do_install():
            api_headers = {'User-Agent': 'Rinkhals-AppStore/1.0'}
            swu_path = f'/tmp/rinkhals-appstore/{app_dir}.swu'

            # Map the printer model to the Rinkhals.Apps SWU asset group, mirroring
            # rinkhals-web's modelToAssetGroup so both installers pick the same build.
            asset_group = {
                'K2P': 'k2p-k3', 'K3': 'k2p-k3', 'K3V2': 'k2p-k3',
                'K3M': 'k3m',
                'KS1': 'ks1', 'KS1M': 'ks1',
            }.get((KOBRA_MODEL_CODE or '').strip().upper())

            if not asset_group:
                with lvr.lock():
                    self.modal_store_install.obj_progress_bar.set_style_bg_color(lvr.COLOR_DANGER, lv.STATE.DEFAULT)
                    self.modal_store_install.label_progress_text.set_text(f'Unsupported model ({KOBRA_MODEL_CODE})')
                return

            try:
                import requests

                # Resolve the model-aware SWU asset from the latest Rinkhals.Apps release,
                # so the TouchUI installs exactly the same build and version as rinkhals-web
                # (avoiding the version skew of copying raw branch files).
                with lvr.lock():
                    self.modal_store_install.label_progress_text.set_text('Finding release...')

                release_url = f'https://api.github.com/repos/{self.APP_STORE_REPO}/releases/latest'
                r = requests.get(release_url, headers=api_headers, timeout=10)
                if r.status_code != 200:
                    raise Exception(f'HTTP {r.status_code} fetching latest release')

                asset_name = f'app-{app_dir}-{asset_group}.swu'
                download_url = next((a.get('browser_download_url')
                                     for a in r.json().get('assets', [])
                                     if a.get('name') == asset_name), None)

                if not download_url:
                    with lvr.lock():
                        self.modal_store_install.obj_progress_bar.set_style_bg_color(lvr.COLOR_DANGER, lv.STATE.DEFAULT)
                        self.modal_store_install.label_progress_text.set_text(f'No build for {KOBRA_MODEL_CODE}')
                    return

                # Download the SWU
                os.makedirs(os.path.dirname(swu_path), exist_ok=True)
                with lvr.lock():
                    self.modal_store_install.label_progress_text.set_text('Downloading...')

                with requests.get(download_url, headers=api_headers, timeout=120, stream=True) as swu_response:
                    swu_response.raise_for_status()
                    total = int(swu_response.headers.get('Content-Length') or 0)
                    downloaded = 0
                    with open(swu_path, 'wb') as f:
                        for chunk in swu_response.iter_content(chunk_size=65536):
                            if self.modal_store_install.has_flag(lv.OBJ_FLAG.HIDDEN):
                                logging.info('App store install canceled.')
                                if os.path.exists(swu_path):
                                    os.remove(swu_path)
                                return
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total:
                                with lvr.lock():
                                    self.modal_store_install.obj_progress_bar.set_width(lv.pct(int(downloaded / total * 90)))

                # Install through tools.sh install_swu, the same path rinkhals-web and the
                # USB-stick installer use (model-aware password + update.sh). shell() only
                # returns stdout, so append a sentinel to recover the exit code.
                with lvr.lock():
                    self.modal_store_install.obj_progress_bar.set_width(lv.pct(95))
                    self.modal_store_install.label_progress_text.set_text('Installing...')
                    self.modal_store_install.button_cancel.add_flag(lv.OBJ_FLAG.HIDDEN)

                output = shell(f'. /useremain/rinkhals/.current/tools.sh && install_swu "{swu_path}"; echo "RINKHALS_RC=$?"')

                if os.path.exists(swu_path):
                    os.remove(swu_path)

                installed_ok = 'RINKHALS_RC=0' in output and os.path.exists(f'{RINKHALS_HOME}/apps/{app_dir}/app.json')
                if not installed_ok:
                    logging.error(f'App store install_swu failed: {output}')
                    with lvr.lock():
                        self.modal_store_install.obj_progress_bar.set_style_bg_color(lvr.COLOR_DANGER, lv.STATE.DEFAULT)
                        self.modal_store_install.label_progress_text.set_text('Install failed')
                    return

                with lvr.lock():
                    self.modal_store_install.obj_progress_bar.set_width(lv.pct(100))
                    self.modal_store_install.label_progress_text.set_text('Installed successfully')
                    self.modal_store_install.button_cancel.add_flag(lv.OBJ_FLAG.HIDDEN)
                    self.modal_store_install.button_done.remove_flag(lv.OBJ_FLAG.HIDDEN)
                    # Refresh detail screen so button shows Remove immediately
                    self.screen_store_app.button_action.clear_event_cb()
                    self.screen_store_app.button_action.set_text('Remove')
                    self.screen_store_app.button_action.set_style_text_color(lvr.COLOR_DANGER, lv.STATE.DEFAULT)
                    self.screen_store_app.button_action.add_event_cb(
                        lambda e, d=app_dir, n=app_name: self.show_text_dialog(
                            f'Remove {n}?\n\nThis will delete all app files.',
                            action='Remove',
                            action_color=lvr.COLOR_DANGER,
                            callback=lambda: self.remove_store_app(d)
                        ),
                        lv.EVENT_CODE.CLICKED, None
                    )

            except Exception as ex:
                if os.path.exists(swu_path):
                    os.remove(swu_path)
                logging.error(f'App store install failed: {ex}')
                with lvr.lock():
                    self.modal_store_install.obj_progress_bar.set_style_bg_color(lvr.COLOR_DANGER, lv.STATE.DEFAULT)
                    self.modal_store_install.label_progress_text.set_text(f'Failed')

        run_async(do_install)

    def remove_store_app(self, app_dir):
        import shutil
        app_path = f'{RINKHALS_HOME}/apps/{app_dir}'

        try:
            if get_app_status(app_dir) != 'stopped':
                stop_app(app_dir)
            disable_app(app_dir)

            if os.path.exists(app_path):
                shutil.rmtree(app_path)

            self.show_screen(self.screen_store)
        except Exception as ex:
            logging.error(f'App store remove failed: {ex}')
            self.show_text_dialog(f'Failed to remove app:\n{ex}')


if __name__ == '__main__':
    logging.info(f'Startup: Python and the imports are done {seconds_since_launch():.1f} s after the menu was launched')
    app = RinkhalsUiApp()
    logging.info(f'Startup: the home screen is built {seconds_since_launch():.1f} s after the menu was launched')
    app.run()
