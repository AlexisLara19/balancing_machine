"""Shared visual tokens for the desktop interface and plots."""
COLORS = {
    'primary': '#004aad',
    'background': '#e9ebed',
    'border': '#c5c5c6',
    'lavender': '#F2EBFF',
    'heading': '#245166',
    'surface': '#ffffff',
    'secondary': '#32629d',
    'text': '#090807',
    'muted': '#555f88',
    'soft': '#f4f4f9',
    'trigger': '#8056ad',
}


def stylesheet():
    c = COLORS
    return f"""
    QWidget {{ font-family: 'Segoe UI', 'DejaVu Sans', sans-serif; font-size: 13px;
               color: {c['text']}; }}
    QMainWindow, QWidget#workspace {{ background: {c['background']}; }}
    QLabel {{ background: transparent; }}
    QLabel#title {{ font-size: 25px; font-weight: 700; color: {c['primary']}; }}
    QLabel#subtitle, QLabel#metricTitle {{ color: {c['muted']}; }}
    QLabel#metricValue {{ font-size: 27px; font-weight: 700; color: {c['primary']}; }}
    QFrame#metricCard {{ background: {c['surface']}; border: 1px solid {c['border']};
                         border-radius: 10px; }}
    QGroupBox {{ background: {c['surface']}; border: 1px solid {c['border']};
                 border-radius: 10px; margin-top: 12px; padding: 18px 12px 12px;
                 font-weight: 600; color: {c['heading']}; }}
    QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left;
                        left: 14px; padding: 0 6px; }}
    QComboBox, QSpinBox, QDoubleSpinBox {{ background: {c['soft']};
        border: 1px solid {c['border']}; border-radius: 5px; padding: 5px 8px;
        min-height: 22px; selection-background-color: {c['primary']}; }}
    QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {c['primary']}; }}
    QComboBox QAbstractItemView {{ background: white; selection-background-color: {c['primary']};
                                 selection-color: white; }}
    QPushButton {{ background: {c['primary']}; color: white; border: 1px solid {c['primary']};
                   border-radius: 6px; padding: 9px 16px; font-weight: 600; }}
    QPushButton:hover {{ background: {c['secondary']}; }}
    QPushButton:pressed {{ background: {c['heading']}; }}
    QPushButton:focus {{ border: 2px solid {c['muted']}; }}
    QLabel#status {{ background: {c['soft']}; color: {c['heading']};
                     border-radius: 5px; padding: 6px; }}
    QLabel#status[state="connected"] {{ color: #176546; background: #e9f5ee; }}
    QLabel#status[state="error"] {{ color: #a12636; background: #fff0f0; }}
    QScrollArea {{ border: none; background: transparent; }}
    QWidget#controls {{ background: transparent; }}
    QScrollBar:vertical {{ background: {c['background']}; width: 10px; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 28px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
