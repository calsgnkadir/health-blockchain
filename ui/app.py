
import customtkinter as ctk
from tkinter import messagebox, simpledialog
import tkinter as tk
from core.blockchain import Blockchain
from core.security import decrypt_data
import database.storage as storage
import json
import time

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

class BlockCard(ctk.CTkFrame):
    """A card representing a single data block item."""
    def __init__(self, master, index, data, is_protected, on_click, is_broken=False):
        # Determine colors based on state
        bg_color = "#2B2B38"
        border_color = "#3A3A4B"
        status_color = "#00E676" # Green
        status_icon = "🔗" 

        if is_broken:
            bg_color = "#3E2723" # Dark Redish
            border_color = "#D32F2F" # Red Border
            status_color = "#D32F2F"
            status_icon = "⛓️‍💥 BROKEN"
        elif is_protected:
            status_color = "#E57373" # Red
            status_icon = "🔒 LOCKED"

        super().__init__(master, corner_radius=15, fg_color=bg_color, border_width=2 if is_broken else 1, border_color=border_color)
        self.on_click = on_click
        self.index = index
        self.data = data
        self.is_protected = is_protected
        
        # Layout
        self.grid_columnconfigure(1, weight=1)
        
        # Header Row
        self.id_label = ctk.CTkLabel(self, text=f"BLOCK #{index}", font=ctk.CTkFont(size=14, weight="bold"), text_color="gray70")
        self.id_label.grid(row=0, column=0, padx=15, pady=(10,5), sticky="w")
        
        self.status_label = ctk.CTkLabel(self, text=status_icon, text_color=status_color, font=ctk.CTkFont(size=12, weight="bold"))
        self.status_label.grid(row=0, column=1, padx=15, pady=(10,5), sticky="e")

        # Separator (Visual Line)
        # self.sep = ctk.CTkFrame(self, height=2, fg_color="gray30")
        # self.sep.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)

        # Title
        display_title = "Unknown Data"
        if isinstance(data, dict):
            display_title = data.get("title", "Untitled")
        elif isinstance(data, str) and is_protected:
            display_title = "••••••••••••"
            
        self.title_lbl = ctk.CTkLabel(self, text=display_title, font=ctk.CTkFont(size=16, weight="bold"), text_color="white")
        self.title_lbl.grid(row=2, column=0, columnspan=2, padx=15, pady=(5, 5), sticky="w")

        # Timestamp (Optional)
        # self.ts_lbl = ctk.CTkLabel(self, text="2024-02-16 12:45", font=ctk.CTkFont(size=10), text_color="gray50")
        # self.ts_lbl.grid(row=3, column=0, columnspan=2, padx=15, sticky="w")

        # Action Button
        btn_text = "INSPECT BLOCK" if not is_broken else "INSPECT DAMAGE"
        btn_fg = "#3D3D50" if not is_broken else "#B71C1C"
        btn_hover = "#4D4D60" if not is_broken else "#FF5252"

        self.view_btn = ctk.CTkButton(
            self, 
            text=btn_text, 
            fg_color=btn_fg, 
            hover_color=btn_hover, 
            height=32,
            font=ctk.CTkFont(size=12),
            command=lambda: self.on_click(self.index)
        )
        self.view_btn.grid(row=4, column=0, columnspan=2, padx=15, pady=15, sticky="ew")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Window Setup
        self.title("SecureChain Vault - Enterprise Edition")
        self.geometry("1100x700")
        
        # Main Layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # ----- Sidebar -----
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color="#1F1F28")
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(4, weight=1)
        
        # App Logo
        self.logo_lbl = ctk.CTkLabel(self.sidebar, text="⛓️ HEALTHCHAIN", font=ctk.CTkFont(size=26, weight="bold"))
        self.logo_lbl.grid(row=0, column=0, padx=20, pady=(30, 40))
        
        # Stats
        self.stats_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.stats_frame.grid(row=1, column=0, sticky="ew", padx=20)
        self.block_count_lbl = ctk.CTkLabel(self.stats_frame, text="Total Blocks: 0", text_color="gray70")
        self.block_count_lbl.pack(anchor="w")
        
        # Actions
        self.add_btn = ctk.CTkButton(
            self.sidebar, 
            text="+ ADD DATA BLOCK", 
            height=45,
            fg_color="#7C4DFF", 
            hover_color="#651FFF",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.open_add_dialog
        )
        self.add_btn.grid(row=2, column=0, padx=20, pady=(30, 15), sticky="ew")
        
        self.verify_btn = ctk.CTkButton(
            self.sidebar, 
            text="🛡️ SYSTEM INTEGRITY CHECK", 
            height=40,
            fg_color="#2CC985", 
            hover_color="#00BFA5",
            text_color="white",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.verify_chain_action
        )
        self.verify_btn.grid(row=3, column=0, padx=20, pady=10, sticky="ew")

        # Simulate Attack (Demo Feature)
        self.attack_btn = ctk.CTkButton(
            self.sidebar,
            text="⚠️ SIMULATE ATTACK",
            fg_color="#D32F2F",
            hover_color="#B71C1C",
            command=self.simulate_attack
        )
        self.attack_btn.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        
        # Footer
        self.footer_lbl = ctk.CTkLabel(self.sidebar, text="v2.0.0 Enterprise\nLMDB Powered", text_color="gray40", font=ctk.CTkFont(size=10))
        self.footer_lbl.grid(row=5, column=0, pady=20)
        
        # ----- Main Storage Feed -----
        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        # Header with Search
        self.header_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.header_frame.pack(fill="x", pady=(0, 20))

        self.main_lbl = ctk.CTkLabel(self.header_frame, text="📦 Blockchain Timeline", font=ctk.CTkFont(size=24, weight="bold"))
        self.main_lbl.pack(side="left")
        
        self.search_entry = ctk.CTkEntry(self.header_frame, placeholder_text="🔍 Filter chain...", width=220)
        self.search_entry.pack(side="right")
        self.search_entry.bind("<KeyRelease>", self.refresh_ui)
        
        # Scrollable Timeline Area
        self.scrollable = ctk.CTkScrollableFrame(self.main_area, fg_color="transparent")
        self.scrollable.pack(fill="both", expand=True)
        
        # Initialize Blockchain
        self.project_name = "SecureVault"
        self.init_blockchain()
        
        # Initial Load
        self.refresh_ui()
        self.verify_chain_on_startup()
        
    def init_blockchain(self):
        # LMDB handles creation automatically if folder is missing
        if not storage.project_exists(self.project_name):
            storage.create_project(self.project_name)
        
        # Initialize (Loads from DB or creates Genesis)
        self.blockchain = Blockchain(self.project_name)
            
    def verify_chain_action(self):
        broken_idx = self.blockchain.find_broken_link_index()
        if broken_idx == -1:
            messagebox.showinfo("System Secure", "✅ SYSTEM INTEGRITY: 100%\nAll hashes and signatures are valid.")
            self.refresh_ui() # Ensure green state
        else:
            messagebox.showerror("CRITICAL ERROR", f"❌ FATAL: Chain broken at Block #{broken_idx}!\nData tampering detected.")
            self.refresh_ui() # Trigger UI update to show red blocks

    def simulate_attack(self):
        """Corrupts a random block to demonstrate integrity check."""
        if len(self.blockchain.chain) < 2:
             messagebox.showinfo("Info", "Add at least 1 data block (besides Genesis) to simulate an attack.")
             return
             
        # Attack the last block for demonstration
        target_index = len(self.blockchain.chain) - 1
        target_block = self.blockchain.chain[target_index]
        
        # Corrupt Data
        original_data = target_block.data
        if isinstance(original_data, dict):
             target_block.data["title"] = "HACKED DATA"
             target_block.data["content"] = "This block has been tampered with!"
        else:
             target_block.data = {"title": "HACKED", "content": "Corrupted Payload"}
             
        # IMPORTANT: We save the block with NEW data but OLD signatures/hash
        # This creates the mismatch.
        self.blockchain.save_block(target_block)
        
        messagebox.showwarning("Attack Simulated", f"⚠️ Block #{target_index} has been corrupted!\n\nIts data was changed, but the cryptographic signature remains invalid.\n\nNow running integrity check...")
        
        self.verify_chain_action()
            
    def verify_chain_on_startup(self):
        if not self.blockchain.is_valid():
             # We can't show broken_idx clearly here without recalculating, 
             # but refresh_ui will handle the coloring if we just call it.
             messagebox.showerror("Security Alert", "❌ CRITICAL SECURITY WARNING\n\nThe blockchain data file appears to be corrupted or tampered with.")

    def refresh_ui(self, event=None):
        # Clear main area
        for widget in self.scrollable.winfo_children():
            widget.destroy()
            
        final_data = self.blockchain.get_final_data()
        search_query = self.search_entry.get().lower().strip() if hasattr(self, 'search_entry') else ""
        
        # Check chain health for coloring
        broken_index = self.blockchain.find_broken_link_index()
        
        # Update Stats
        total = len(self.blockchain.chain)
        self.block_count_lbl.configure(text=f"Total Chain Height: {total}")
        
        # Sort by latest (Top of timeline) to oldest (Bottom)
        # Or oldest to newest? Timelines usually go down. Let's do Newest at Top.
        sorted_indices = sorted(final_data.keys(), reverse=True)
        
        # We need a single column for the timeline
        self.scrollable.grid_columnconfigure(0, weight=1)

        row_counter = 0

        for index in sorted_indices:
            data = final_data[index]
            
            # Filter Logic
            if search_query:
                # Prepare searchable text
                searchable_text = ""
                if isinstance(data, dict):
                    searchable_text = (str(data.get("title", "")) + " " + str(data.get("content", ""))).lower()
                elif isinstance(data, str):
                    searchable_text = data.lower()
                
                # If it's a match?
                if search_query not in searchable_text:
                    continue # Skip this block
            
            # Determine if this block is part of the "broken chain" segment
            # If broken_index is 5, then blocks 5, 6, 7... are invalid.
            # (Since we are sorting reverse, we check if index >= broken_index)
            is_broken = False
            if broken_index != -1 and index >= broken_index:
                is_broken = True

            # Identify Protection
            is_protected = False
            original_block = self.blockchain.chain[index]
            is_protected = original_block.is_protected
            
            # Create Card
            card = BlockCard(self.scrollable, index, data, is_protected, self.open_block_viewer, is_broken=is_broken)
            card.grid(row=row_counter, column=0, padx=50, pady=(0, 0), sticky="ew") # Padding handled by connector
            
            # Add Connector Line (Below card, unless it's the very last item displayed)
            # In reverse sort, the "last" item in loop is the genesis block (index 0).
            # We want connectors BETWEEN blocks.
            if index > 0:
                connector_color = "#555"
                if is_broken:
                     connector_color = "#D32F2F"
                
                # Draw a simple frame as a line
                conn = ctk.CTkFrame(self.scrollable, width=4, height=30, fg_color=connector_color)
                conn.grid(row=row_counter+1, column=0, pady=0)
                
            row_counter += 2

    def open_add_dialog(self):
        # Simple Input Dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add New Data Block")
        dialog.geometry("500x400")
        dialog.attributes("-topmost", True)
        
        def save():
            label = title_entry.get().strip()
            payload = content_text.get("0.0", "end").strip()
            protected = switch_var.get() == 1
            
            if not label:
                return
            
            password = None
            if protected:
                password = ctk.CTkInputDialog(text="Create Password for this Block:", title="Encryption").get_input()
                if not password:
                    return
            
            data = {"title": label, "content": payload}
            self.blockchain.add_block(data, is_protected=protected, protection_password=password)
            self.refresh_ui() # Save is implicit in add_block now
            dialog.destroy()
            messagebox.showinfo("Success", "Block successfully mined and added to chain!")

        # UI for Dialog
        ctk.CTkLabel(dialog, text="Block Label:", font=ctk.CTkFont(size=14)).pack(anchor="w", padx=20, pady=(20, 5))
        title_entry = ctk.CTkEntry(dialog, placeholder_text="e.g. My Wallet Seeds")
        title_entry.pack(fill="x", padx=20)
        
        ctk.CTkLabel(dialog, text="Data Payload:", font=ctk.CTkFont(size=14)).pack(anchor="w", padx=20, pady=(15, 5))
        content_text = ctk.CTkTextbox(dialog, height=100)
        content_text.pack(fill="x", padx=20)
        
        switch_var = ctk.IntVar(value=0)
        ctk.CTkSwitch(dialog, text="Encrypt & Lock Data", variable=switch_var).pack(anchor="w", padx=20, pady=20)
        
        ctk.CTkButton(dialog, text="MINE & STORE", command=save, fg_color="#7C4DFF").pack(fill="x", padx=20, pady=10)

    def open_block_viewer(self, index):
        # Retrieve Block
        original_block = self.blockchain.chain[index]
        final_data = self.blockchain.get_final_data().get(index)
        
        # Create Viewer Window Immediately
        viewer = ctk.CTkToplevel(self)
        viewer.title(f"Block #{index} Inspection")
        viewer.geometry("600x550")
        viewer.attributes("-topmost", True) # Ensure it's visible
        
        # Header
        header_frame = ctk.CTkFrame(viewer, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(header_frame, text=f"BLOCK #{index}", font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")
        
        status_text = "🔒 ENCRYPTED" if original_block.is_protected else "📖 PUBLIC"
        status_color = "#E57373" if original_block.is_protected else "#00E676"
        ctk.CTkLabel(header_frame, text=status_text, text_color=status_color, font=ctk.CTkFont(size=14, weight="bold")).pack(side="right")

        # Content Area
        content_frame = ctk.CTkFrame(viewer)
        content_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        # Helper to populate content
        def show_content(title, content, is_locked=False):
            for widget in content_frame.winfo_children():
                widget.destroy()
                
            if is_locked:
                # Locked State UI
                center_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
                center_frame.place(relx=0.5, rely=0.5, anchor="center")
                
                ctk.CTkLabel(center_frame, text="🔒", font=ctk.CTkFont(size=40)).pack(pady=10)
                ctk.CTkLabel(center_frame, text="This block is encrypted.", font=ctk.CTkFont(size=16)).pack()
                ctk.CTkButton(center_frame, text="🔓 DECRYPT & VIEW DATA", command=unlock_data, fg_color="#E040FB").pack(pady=20)
                return

            # Unlocked/Normal State UI
            ctk.CTkLabel(content_frame, text="Label / Title:", text_color="gray").pack(anchor="w", padx=15, pady=(15, 5))
            ctk.CTkLabel(content_frame, text=title, font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=15)
            
            ctk.CTkLabel(content_frame, text="Data Payload:", text_color="gray").pack(anchor="w", padx=15, pady=(15, 5))
            
            txt = ctk.CTkTextbox(content_frame, font=ctk.CTkFont(family="Consolas", size=14))
            txt.pack(fill="both", expand=True, padx=15, pady=10)
            txt.insert("0.0", content)
            txt.configure(state="disabled")
            
            # Correction Button (Only show if unlocked)
            ctk.CTkButton(viewer, text="APPEND CORRECTION / UPDATE", fg_color="#7C4DFF", 
                          command=lambda: [viewer.destroy(), self.open_edit_dialog(index, title, content, original_block.is_protected)]
                         ).pack(fill="x", padx=20, pady=20)

        def unlock_data():
            pwd = ctk.CTkInputDialog(text=f"Enter Password for Block #{index}:", title="Decrypt").get_input()
            if not pwd:
                return
                
            # Verify password via checking block data
            block_check = self.blockchain.get_block_data(index, pwd)
            if isinstance(block_check, str) and (block_check.startswith("❌") or block_check.startswith("🔒")):
                 messagebox.showerror("Error", "Incorrect Password")
                 return
            
            # Decrypt final data if necessary
            curr_title = "Unknown"
            curr_content = "Error Decrypting"
            
            # Try to decrypt the LATEST data (final_data) which might be just an encrypted string
            try:
                # If final_data is string, try to decrypt it. If it's already dict (unlikely for protected), use it.
                data_to_decrypt = final_data
                if isinstance(data_to_decrypt, str):
                    decrypted_json = decrypt_data(data_to_decrypt, pwd)
                    data_obj = json.loads(decrypted_json)
                    curr_title = data_obj.get("title", "")
                    curr_content = data_obj.get("content", "")
                else: 
                    # Fallback
                    curr_title = data_to_decrypt.get("title", "") if isinstance(data_to_decrypt, dict) else "Unknown"
                    curr_content = str(data_to_decrypt)
                
                # Show unlocked content
                show_content(curr_title, curr_content, is_locked=False)
                
            except Exception as e:
                messagebox.showerror("Decryption Error", f"Failed to decrypt payload: {e}")

        # Initial View Logic
        if original_block.is_protected:
            show_content(None, None, is_locked=True)
        else:
            # Not protected, just show
            t = final_data.get("title", "Untitled") if isinstance(final_data, dict) else "Data"
            c = final_data.get("content", "") if isinstance(final_data, dict) else str(final_data)
            show_content(t, c, is_locked=False)

    def open_edit_dialog(self, index, old_title, old_content, is_protected):
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Correcting Block #{index}")
        dialog.geometry("500x450")
        
        ctk.CTkLabel(dialog, text=f"New Version for Block #{index}", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)
        
        ctk.CTkLabel(dialog, text="Label:").pack(anchor="w", padx=20)
        title_entry = ctk.CTkEntry(dialog)
        title_entry.insert(0, old_title)
        title_entry.pack(fill="x", padx=20)
        
        ctk.CTkLabel(dialog, text="Content:").pack(anchor="w", padx=20)
        content_text = ctk.CTkTextbox(dialog, height=150)
        content_text.insert("0.0", old_content)
        content_text.pack(fill="x", padx=20)
        
        def save_correction():
            new_title = title_entry.get().strip()
            new_content = content_text.get("0.0", "end").strip()
            
            pwd = None
            if is_protected:
                pwd = ctk.CTkInputDialog(text="Enter Password to Encrypt New Version:", title="Security").get_input()
                if not pwd:
                     return
            
            new_data = {"title": new_title, "content": new_content}
            self.blockchain.add_correction_block(index, new_data, encryption_password=pwd)
            self.refresh_ui() # Save is implicit
            dialog.destroy()
            messagebox.showinfo("Success", "Correction Block added to Chain!")
            
        ctk.CTkButton(dialog, text="COMMIT CORRECTION", fg_color="#E040FB", command=save_correction).pack(fill="x", padx=20, pady=20)

if __name__ == "__main__":
    app = App()
    app.mainloop()
