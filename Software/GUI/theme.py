"""
theme.py - Dark theme styling for Drone Control Center
"""
import tkinter as tk
from tkinter import ttk


# ── Color palette ──
COLORS = {
    # Backgrounds
    'bg_dark':       '#1a1b26',   # Main window background
    'bg_mid':        '#24283b',   # Frames, panels
    'bg_light':      '#2f3347',   # Inputs, listboxes
    'bg_hover':      '#3b3f54',   # Hover states
    'bg_selected':   '#394b70',   # Selected items

    # Foregrounds
    'fg_primary':    '#c0caf5',   # Main text
    'fg_secondary':  '#9aa5ce',   # Secondary / dimmed text
    'fg_muted':      '#565f89',   # Placeholders, hints
    'fg_bright':     '#e0e6ff',   # Headings, emphasis

    # Accent colors
    'accent_blue':   '#7aa2f7',   # Primary accent / buttons
    'accent_green':  '#9ece6a',   # Success / running
    'accent_red':    '#f7768e',   # Error / stopped
    'accent_yellow': '#e0af68',   # Warning
    'accent_cyan':   '#7dcfff',   # Info / links
    'accent_purple': '#bb9af7',   # Tags / labels

    # Borders
    'border':        '#3b3f54',
    'border_focus':  '#7aa2f7',

    # Terminal
    'term_bg':       '#13141c',
    'term_fg':       '#73daca',

    # Buttons
    'btn_bg':        '#3d59a1',
    'btn_fg':        '#c0caf5',
    'btn_hover':     '#4e6bb5',
    'btn_pressed':   '#2e4480',
    'btn_disabled':  '#2a2d3d',

    # Tab bar
    'tab_bg':        '#1f2132',
    'tab_selected':  '#24283b',
    'tab_fg':        '#9aa5ce',
    'tab_fg_active': '#7aa2f7',
}


def apply_theme(root: tk.Tk):
    """Apply the dark theme to the entire application"""

    style = ttk.Style(root)

    # Use 'clam' as base — it's the most customisable built-in theme
    style.theme_use('clam')

    c = COLORS

    # ── Root window ──
    root.configure(bg=c['bg_dark'])

    # ── TFrame ──
    style.configure('TFrame', background=c['bg_dark'])

    # ── TLabel ──
    style.configure('TLabel',
                    background=c['bg_dark'],
                    foreground=c['fg_primary'],
                    font=('Segoe UI', 10))

    # Heading style for the title
    style.configure('Title.TLabel',
                    background=c['bg_dark'],
                    foreground=c['fg_bright'],
                    font=('Segoe UI', 16, 'bold'))

    # Status labels (green / red / gray are set at runtime, but base style here)
    style.configure('Status.TLabel',
                    background=c['bg_dark'],
                    font=('Segoe UI', 10, 'bold'))

    style.configure('StatusGreen.TLabel',
                    background=c['bg_dark'],
                    foreground=c['accent_green'],
                    font=('Segoe UI', 10, 'bold'))

    style.configure('StatusRed.TLabel',
                    background=c['bg_dark'],
                    foreground=c['accent_red'],
                    font=('Segoe UI', 10, 'bold'))

    style.configure('StatusGray.TLabel',
                    background=c['bg_dark'],
                    foreground=c['fg_muted'],
                    font=('Segoe UI', 10, 'bold'))

    # ── TLabelframe ──
    style.configure('TLabelframe',
                    background=c['bg_mid'],
                    foreground=c['fg_primary'],
                    bordercolor=c['border'],
                    lightcolor=c['border'],
                    darkcolor=c['border'])
    style.configure('TLabelframe.Label',
                    background=c['bg_mid'],
                    foreground=c['accent_cyan'],
                    font=('Segoe UI', 10, 'bold'))

    # ── TNotebook (tabs) ──
    style.configure('TNotebook',
                    background=c['bg_dark'],
                    bordercolor=c['border'],
                    lightcolor=c['border'],
                    darkcolor=c['border'])
    style.configure('TNotebook.Tab',
                    background=c['tab_bg'],
                    foreground=c['tab_fg'],
                    padding=[14, 6],
                    font=('Segoe UI', 10))
    style.map('TNotebook.Tab',
              background=[('selected', c['tab_selected']),
                          ('active', c['bg_hover'])],
              foreground=[('selected', c['tab_fg_active']),
                          ('active', c['fg_bright'])],
              expand=[('selected', [1, 1, 1, 0])])

    # ── TButton ──
    style.configure('TButton',
                    background=c['btn_bg'],
                    foreground=c['btn_fg'],
                    bordercolor=c['border'],
                    lightcolor=c['btn_bg'],
                    darkcolor=c['btn_bg'],
                    focuscolor=c['border_focus'],
                    padding=[10, 5],
                    font=('Segoe UI', 10))
    style.map('TButton',
              background=[('active', c['btn_hover']),
                          ('pressed', c['btn_pressed']),
                          ('disabled', c['btn_disabled'])],
              foreground=[('disabled', c['fg_muted'])])

    # Accent button style (for primary actions like Launch, Run)
    style.configure('Accent.TButton',
                    background=c['accent_blue'],
                    foreground='#ffffff',
                    bordercolor=c['accent_blue'],
                    lightcolor=c['accent_blue'],
                    darkcolor=c['accent_blue'],
                    padding=[10, 6],
                    font=('Segoe UI', 10, 'bold'))
    style.map('Accent.TButton',
              background=[('active', '#8fb3ff'),
                          ('pressed', '#5a7ec7'),
                          ('disabled', c['btn_disabled'])],
              foreground=[('disabled', c['fg_muted'])])

    # Danger button style (for Stop)
    style.configure('Danger.TButton',
                    background=c['accent_red'],
                    foreground='#ffffff',
                    bordercolor=c['accent_red'],
                    lightcolor=c['accent_red'],
                    darkcolor=c['accent_red'],
                    padding=[10, 6],
                    font=('Segoe UI', 10, 'bold'))
    style.map('Danger.TButton',
              background=[('active', '#ff8fa0'),
                          ('pressed', '#d45568'),
                          ('disabled', c['btn_disabled'])],
              foreground=[('disabled', c['fg_muted'])])

    # Success button style
    style.configure('Success.TButton',
                    background=c['accent_green'],
                    foreground='#1a1b26',
                    bordercolor=c['accent_green'],
                    lightcolor=c['accent_green'],
                    darkcolor=c['accent_green'],
                    padding=[10, 6],
                    font=('Segoe UI', 10, 'bold'))
    style.map('Success.TButton',
              background=[('active', '#b5e08a'),
                          ('pressed', '#7aab4e'),
                          ('disabled', c['btn_disabled'])],
              foreground=[('disabled', c['fg_muted'])])

    # ── TEntry ──
    style.configure('TEntry',
                    fieldbackground=c['bg_light'],
                    foreground=c['fg_primary'],
                    bordercolor=c['border'],
                    lightcolor=c['border'],
                    darkcolor=c['border'],
                    insertcolor=c['fg_primary'],
                    padding=[6, 4])
    style.map('TEntry',
              fieldbackground=[('focus', c['bg_light']),
                               ('disabled', c['bg_dark'])],
              bordercolor=[('focus', c['border_focus'])])

    # ── TCombobox ──
    style.configure('TCombobox',
                    fieldbackground=c['bg_light'],
                    foreground=c['fg_primary'],
                    background=c['bg_light'],
                    bordercolor=c['border'],
                    lightcolor=c['border'],
                    darkcolor=c['border'],
                    arrowcolor=c['fg_secondary'],
                    padding=[6, 4])
    style.map('TCombobox',
              fieldbackground=[('readonly', c['bg_light'])],
              foreground=[('readonly', c['fg_primary'])],
              bordercolor=[('focus', c['border_focus'])])
    # Style the dropdown list
    root.option_add('*TCombobox*Listbox.background', c['bg_light'])
    root.option_add('*TCombobox*Listbox.foreground', c['fg_primary'])
    root.option_add('*TCombobox*Listbox.selectBackground', c['bg_selected'])
    root.option_add('*TCombobox*Listbox.selectForeground', c['fg_bright'])

    # ── TScrollbar ──
    style.configure('TScrollbar',
                    background=c['bg_mid'],
                    troughcolor=c['bg_dark'],
                    bordercolor=c['bg_dark'],
                    lightcolor=c['bg_mid'],
                    darkcolor=c['bg_mid'],
                    arrowcolor=c['fg_secondary'])
    style.map('TScrollbar',
              background=[('active', c['bg_hover'])])

    # ── TSeparator ──
    style.configure('TSeparator', background=c['border'])

    # ── Listbox defaults (not ttk — use option_add) ──
    root.option_add('*Listbox.background', c['bg_light'])
    root.option_add('*Listbox.foreground', c['fg_primary'])
    root.option_add('*Listbox.selectBackground', c['bg_selected'])
    root.option_add('*Listbox.selectForeground', c['fg_bright'])
    root.option_add('*Listbox.highlightBackground', c['bg_dark'])
    root.option_add('*Listbox.highlightColor', c['border_focus'])
    root.option_add('*Listbox.borderWidth', 1)
    root.option_add('*Listbox.relief', 'flat')

    # ── Text widget defaults ──
    root.option_add('*Text.background', c['bg_light'])
    root.option_add('*Text.foreground', c['fg_primary'])
    root.option_add('*Text.insertBackground', c['fg_primary'])
    root.option_add('*Text.selectBackground', c['bg_selected'])
    root.option_add('*Text.selectForeground', c['fg_bright'])
    root.option_add('*Text.highlightBackground', c['bg_dark'])
    root.option_add('*Text.highlightColor', c['border_focus'])
    root.option_add('*Text.relief', 'flat')


def get_terminal_colors() -> dict:
    """Return colors for terminal/log widgets"""
    return {
        'bg': COLORS['term_bg'],
        'fg': COLORS['term_fg'],
        'select_bg': COLORS['bg_selected'],
        'select_fg': COLORS['fg_bright'],
    }


def get_colors() -> dict:
    """Return the full color palette for use in custom widgets"""
    return dict(COLORS)