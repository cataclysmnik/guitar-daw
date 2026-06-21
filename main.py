import os
os.environ["SD_ENABLE_ASIO"] = "1"

# Import and initialize pedalboard early to force C++/JUCE/COM initialization
# before PySide6/Qt creates its QApplication/thread structures.
import numpy as np
import pedalboard
try:
    _dummy_board = pedalboard.Pedalboard([])
    _dummy_board(np.zeros((2, 128), dtype=np.float32), 44100)
except Exception:
    pass

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from widgets.main_window import MainWindow
from widgets.splash import GraphiteSplashScreen

def main():
    # Setup application properties
    QApplication.setApplicationName("Graphite DAW")
    QApplication.setApplicationDisplayName("Graphite DAW")
    QApplication.setOrganizationName("Graphite Studio")
    
    # Initialize PySide Application
    app = QApplication(sys.argv)
    
    from PySide6.QtGui import QIcon
    from theme_utils import get_resource_path
    logo_path = get_resource_path("logo.png")
    if os.path.exists(logo_path):
        app.setWindowIcon(QIcon(logo_path))
    
    # Create and show startup splash screen
    splash = GraphiteSplashScreen()
    splash.show()
    app.processEvents()
    
    # Create the DAW Main Window interface
    window = MainWindow(splash=splash)
    
    window.showMaximized()
    window.raise_()
    window.activateWindow()
    
    # Must apply after show() so Windows correctly registers the active native HWND
    from theme_utils import apply_dark_titlebar
    apply_dark_titlebar(window)
    
    # Close the splash screen after the main window is fully loaded
    splash.finish(window)
    
    # Run event loop
    exit_code = app.exec()
    
    # Clean up temp VSTs on exit
    try:
        from audio_engine import clean_temp_vsts
        clean_temp_vsts()
    except Exception:
        pass
        
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
