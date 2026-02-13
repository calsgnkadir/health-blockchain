
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
    def __init__(self, master, index, data, is_protected, on_click):
        super().__init__(master, corner_radius=15, fg_color="#2B2B38", border_width=1, border_color="#3A3A4B")
        self.on_click = on_click
        self.index = index
        self.data = data
        self.is_protected = is_protected
        
        # Grid layout
        self.grid_columnconfigure(1, weight=1)
        
        # Icon / Status
        status_color = "#E57373" if is_protected else "#00E676" # Red/Green
        status_text = "🔒 LCS (Locked)" if is_protected else "📖 D-BLOCK (Open)"
        
        self.status_bar = ctk.CTkFrame(self, height=5, fg_color=status_color, corner_radius=5)
        self.status_bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 5))
        
        # Block Header
        self.id_label = ctk.CTkLabel(self, text=f"BLOCK ID: #{index}", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray60")
        self.id_label.grid(row=1, column=0, padx=15, sticky="w")
        
        self.type_label = ctk.CTkLabel(self, text=status_text, font=ctk.CTkFont(size=10), text_color=status_color)
        self.type_label.grid(row=1, column=1, padx=15, sticky="e")
        
        # Title / Label
        display_title = "Unknown Data"
        if isinstance(data, dict):
            display_title = data.get("title", "Untitled")
        elif isinstance(data, str) and is_protected:
            display_title = "••••••••••••"
            
        self.title_lbl = ctk.CTkLabel(self, text=display_title, font=ctk.CTkFont(size=18, weight="bold"), text_color="white")
        self.title_lbl.grid(row=2, column=0, columnspan=2, padx=15, pady=(5, 10), sticky="w")
        
        # Action Button
        self.view_btn = ctk.CTkButton(
            self, 
            text="ACCESS DATA", 
            fg_color="#3D3D50", 
            hover_color="#4D4D60", 
            height=32,
            command=lambda: self.on_click(self.index)
        )
        self.view_btn.grid(row=3, column=0, columnspan=2, padx=15, pady=(0, 15), sticky="ew")
        
    def set_content(self, title):
        self.title_lbl.configure(text=title)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Window Setup
        self.title("SecureChain Vault")
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
        
        # Footer
        self.footer_lbl = ctk.CTkLabel(self.sidebar, text="v1.2.0 Stable\nSecure Storage", text_color="gray40", font=ctk.CTkFont(size=10))
        self.footer_lbl.grid(row=5, column=0, pady=20)
        
        # ----- Main Storage Feed -----
        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        self.main_lbl = ctk.CTkLabel(self.main_area, text="📦 Storage Blocks", font=ctk.CTkFont(size=24, weight="bold"))
        self.main_lbl.pack(anchor="w", pady=(0, 20))
        
        self.scrollable = ctk.CTkScrollableFrame(self.main_area, fg_color="transparent")
        self.scrollable.pack(fill="both", expand=True)
        
        # Initialize Blockchain
        self.project_name = "SecureVault"
        self.init_blockchain()
        
        # Initial Load
        self.refresh_ui()
        self.verify_chain_on_startup()
        
    def init_blockchain(self):
        if not storage.project_exists(self.project_name):
            storage.create_project(self.project_name)
            self.blockchain = Blockchain(self.project_name)
            self.blockchain.save_chain()
        else:
            bc = Blockchain.load_chain(self.project_name)
            self.blockchain = bc if bc else Blockchain(self.project_name)
            
    def verify_chain_action(self):
        if self.blockchain.is_valid():
            messagebox.showinfo("System Secure", "✅ SYSTEM INTEGRITY: 100%\nAll hashes and signatures are valid.")
        else:
            messagebox.showerror("CRITICAL ERROR", "❌ FATAL: Blockchain integrity corrupted!\nData tampering detected.")
            
    def verify_chain_on_startup(self):
        if not self.blockchain.is_valid():
            messagebox.showerror("Security Alert", "❌ CRITICAL SECURITY WARNING\n\nThe blockchain data file appears to be corrupted or tampered with.")

    def refresh_ui(self):
        # Clear main area
        for widget in self.scrollable.winfo_children():
            widget.destroy()
            
        final_data = self.blockchain.get_final_data()
        
        # Update Stats
        total = len(self.blockchain.chain)
        self.block_count_lbl.configure(text=f"Total Chain Height: {total}")
        
        # Sort by latest
        sorted_indices = sorted(final_data.keys(), reverse=True)
        
        # Grid layout for cards (3 columns)
        column_count = 0
        row_count = 0
        
        self.scrollable.grid_columnconfigure(0, weight=1)
        self.scrollable.grid_columnconfigure(1, weight=1)
        self.scrollable.grid_columnconfigure(2, weight=1)

        for index in sorted_indices:
            data = final_data[index]
            
            # Identify Protection
            is_encrypted = False
            is_protected = False
            
            # Check original block for protection flag
            original_block = self.blockchain.chain[index]
            is_protected = original_block.is_protected
            
            if isinstance(data, str) and is_protected:
                is_encrypted = True
            
            # Create Card
            card = BlockCard(self.scrollable, index, data, is_protected, self.open_block_viewer)
            card.grid(row=row_count, column=column_count, padx=10, pady=10, sticky="nsew")
            
            column_count += 1
            if column_count >= 3:
                column_count = 0
                row_count += 1

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
            self.blockchain.save_chain()
            self.refresh_ui()
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
        
        content_to_show = "No Data"
        title_to_show = "Unknown"
        
        if original_block.is_protected:
            pwd = ctk.CTkInputDialog(text=f"Enter Password to Decrypt Block #{index}:", title="Restricted Access").get_input()
            if not pwd:
                return
            
            # Check Password & Decrypt
            # Re-implementing logic here for UI feedback
            # Ideally this should be a method in Blockchain class returning (status, data)
            block_data = self.blockchain.get_block_data(index, pwd)
            
            if block_data == "❌ INCORRECT PASSWORD" or block_data == "🔒 PROTECTED — password required":
                messagebox.showerror("Access Denied", "Incorrect Password. Access Logged.")
                return
            
            # If we are here, blockchain.get_block_data returned the raw data (which might be the dict or the string if decryption failed inside?)
            # Wait, my previous edit to `get_block_data` handles decryption and returns the dict/str.
            
            # Need to handle if decryption failed inside get_block_data (it returns a string starting with DECRYPTION FAILED)
            if isinstance(block_data, str) and block_data.startswith("❌ DECRYPTION FAILED"):
                 messagebox.showerror("Error", block_data)
                 return
                 
            # If we are editing, we need to check if there were corrections.
            # get_block_data returns the BLOCK'S data. But if there are corrections, we want the FINAL data.
            # But the FINAL data is in `final_data` which is encrypted string.
            # So we need to decrypt `final_data` (the latest version) using the password.
            
            # Let's try to decrypt the `final_data` (current state)
            current_state_data = final_data
            if isinstance(current_state_data, str):
                try:
                    decrypted = decrypt_data(current_state_data, pwd)
                    # Try json
                    try:
                        data_obj = json.loads(decrypted)
                        title_to_show = data_obj.get("title", "Untitled")
                        content_to_show = data_obj.get("content", "")
                    except:
                        content_to_show = decrypted
                        title_to_show = "Raw Data"
                except Exception as e:
                    messagebox.showerror("Error", f"Decryption failed on latest data: {e}")
                    return
            else:
                 # Maybe it wasn't encrypted in the latest version (unlikely if protection is on)
                 title_to_show = current_state_data.get("title", "")
                 content_to_show = current_state_data.get("content", "")
        
        else:
            # Not protected
            data_obj = final_data
            if isinstance(data_obj, dict):
                title_to_show = data_obj.get("title", "Untitled")
                content_to_show = data_obj.get("content", "")
            else:
                content_to_show = str(data_obj)

        # Show Viewer Window
        viewer = ctk.CTkToplevel(self)
        viewer.title(f"Block #{index} Content")
        viewer.geometry("600x500")
        
        ctk.CTkLabel(viewer, text=f"BLOCK #{index} DATA", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)
        
        ctk.CTkLabel(viewer, text="Label:", text_color="gray").pack(anchor="w", padx=20)
        ctk.CTkLabel(viewer, text=title_to_show, font=ctk.CTkFont(size=16)).pack(anchor="w", padx=20, pady=(0, 20))
        
        ctk.CTkLabel(viewer, text="Decrypted Payload:", text_color="gray").pack(anchor="w", padx=20)
        txt = ctk.CTkTextbox(viewer, font=ctk.CTkFont(family="Consolas", size=14))
        txt.pack(fill="both", expand=True, padx=20, pady=10)
        txt.insert("0.0", content_to_show)
        txt.configure(state="disabled")
        
        # Edit/Correction Button
        def open_edit():
            viewer.destroy()
            self.open_edit_dialog(index, title_to_show, content_to_show, original_block.is_protected)
            
        ctk.CTkButton(viewer, text="APPEND CORRECTION BLOCK", fg_color="#E040FB", command=open_edit).pack(pady=20)

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
            self.blockchain.save_chain()
            self.refresh_ui()
            dialog.destroy()
            messagebox.showinfo("Success", "Correction Block added to Chain!")
            
        ctk.CTkButton(dialog, text="COMMIT CORRECTION", fg_color="#E040FB", command=save_correction).pack(fill="x", padx=20, pady=20)

if __name__ == "__main__":
    app = App()
    app.mainloop()
