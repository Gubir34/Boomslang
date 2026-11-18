"""Style parts of a widget, LVGL's values (lv_obj.h).

lv.PART can't be used on the printer: the generated binding defines class PART
twice, and the second one (with only TEXTAREA_PLACEHOLDER) replaces the first,
so lv.PART.MAIN does not exist. tests/test_liquid.py checks these against the
binding. A part and a state combine as one number (PART_INDICATOR | STATE.CHECKED).
"""

PART_MAIN = 0x000000
PART_INDICATOR = 0x020000
PART_KNOB = 0x030000
