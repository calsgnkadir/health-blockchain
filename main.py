import sys
import os

# Add project root directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Start the application directly
from ui.app import App

if __name__ == "__main__":
    # High DPI settings check (optional, fails silently if not Windows)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = App()
    app.mainloop()
