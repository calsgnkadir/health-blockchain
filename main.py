
import sys
import os
import io

# Set standard output to UTF-8 to handle emojis in console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Ensure we can import from local directories
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import customtkinter
except ImportError:
    # Use ASCII fallback for error message if encoding fails before reconfiguration (unlikely)
    print("X CustomTkinter not found!")
    print("Please install it using: pip install customtkinter")
    print("Or: pip install packaging customtkinter")
    input("Press Enter to exit...")
    sys.exit(1)

from ui.app import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
