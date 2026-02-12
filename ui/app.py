
import customtkinter as ctk
from tkinter import messagebox, simpledialog
from core.blockchain import Blockchain
import database.storage as storage
import json

ctk.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Window Setup
        self.title("Blockchain Notebook")
        self.geometry("1000x600")
        
        # Layout Config
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # ----- Sidebar (Notes List) -----
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(2, weight=1) # List expands
        
        # Logo / Title
        self.logo_label = ctk.CTkLabel(self.sidebar, text="📒 BlockNotes", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        # New Note Button
        self.new_note_btn = ctk.CTkButton(self.sidebar, text="+ New Note", command=self.new_note_action)
        self.new_note_btn.grid(row=1, column=0, padx=20, pady=10)
        
        # Helper for list
        self.scrollable_frame = ctk.CTkScrollableFrame(self.sidebar, label_text="Your Notes")
        self.scrollable_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        
        # Bottom sidebar buttons
        self.verify_btn = ctk.CTkButton(self.sidebar, text="🛡️ Verify Chain", fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"), command=self.verify_chain_action)
        self.verify_btn.grid(row=3, column=0, padx=20, pady=10)
        
        # ----- Main Area (Editor) -----
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)
        
        # Title Entry
        self.title_entry = ctk.CTkEntry(self.main_frame, placeholder_text="Note Title", font=ctk.CTkFont(size=24, weight="bold"), height=50, border_width=0)
        self.title_entry.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        # Content Text
        self.content_text = ctk.CTkTextbox(self.main_frame, font=ctk.CTkFont(size=16), wrap="word")
        self.content_text.grid(row=1, column=0, sticky="nsew")
        
        # Action Buttons Frame
        self.actions_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.actions_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        
        self.status_label = ctk.CTkLabel(self.actions_frame, text="Ready", text_color="gray")
        self.status_label.pack(side="left")
        
        self.save_btn = ctk.CTkButton(self.actions_frame, text="Save to Blockchain", command=self.save_note_action)
        self.save_btn.pack(side="right")
        
        # Protected Toggle
        self.is_protected_var = ctk.IntVar(value=0)
        self.protected_switch = ctk.CTkSwitch(self.actions_frame, text="🔒 Protect", variable=self.is_protected_var)
        self.protected_switch.pack(side="right", padx=10)
        
        # ----- Initialize Blockchain -----
        self.project_name = "MyNotebook"
        self.init_blockchain()
        
        # State
        self.current_block_index = None # None means new note
        self.refresh_notes_list()

    def init_blockchain(self):
        if not storage.project_exists(self.project_name):
            storage.create_project(self.project_name)
            self.blockchain = Blockchain(self.project_name)
            self.blockchain.save_chain()
        else:
            bc = Blockchain.load_chain(self.project_name)
            self.blockchain = bc if bc else Blockchain(self.project_name)
            
    def new_note_action(self):
        self.current_block_index = None
        self.title_entry.delete(0, "end")
        self.content_text.delete("0.0", "end")
        self.is_protected_var.set(0)
        self.status_label.configure(text="New Note")
        
    def save_note_action(self):
        title = self.title_entry.get().strip()
        content = self.content_text.get("0.0", "end").strip()
        
        if not title:
            messagebox.showwarning("Warning", "Title cannot be empty")
            return
            
        note_data = {"title": title, "content": content}
        
        is_protected = self.is_protected_var.get() == 1
        password = None
        
        if is_protected:
            password = ctk.CTkInputDialog(text="Enter password for this note:", title="Password Protection").get_input()
            if not password:
                messagebox.showwarning("Cancelled", "Protection requires a password.")
                return

        if self.current_block_index is None:
            # Add New Block
            self.blockchain.add_block(note_data, is_protected=is_protected, protection_password=password)
            self.status_label.configure(text="Note added to blockchain!")
        else:
            # Edit existing block (Correction)
            # Find the original index if it's already a correction? 
            # Logic: If I edit block #5, I add a new block saying "Correction of #5"
            self.blockchain.add_correction_block(self.current_block_index, note_data)
            self.status_label.configure(text=f"Correction added for Block #{self.current_block_index}")
            
        self.blockchain.save_chain()
        self.refresh_notes_list()
        self.new_note_action() # Clear after save
        
    def refresh_notes_list(self):
        # Clear list
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
            
        final_data = self.blockchain.get_final_data()
        
        # Only show items that look like notes (dict with title)
        # Also need to associate them with the KEY (Block Index)
        
        sorted_indices = sorted(final_data.keys(), reverse=True)
        
        for index in sorted_indices:
            data = final_data[index]
            if not isinstance(data, dict): 
                continue # Skip Genesis or simple string blocks
            
            if "title" not in data:
                continue
                
            # Check protection status using READ BLOCK (password check logic is in backend)
            # But get_final_data returns the pure data because it iterates chain. 
            # Wait, get_final_data in blockchain.py assumes raw data access. 
            # In a real app we'd check protection BEFORE showing title if title was encrypted.
            # But here only whole block content is protected?
            # healthchain.py: get_block_data checks password.
            # get_final_data accesses .data directly.
            # If block.is_protected, .data is visible? 
            # Ah, in Block class .data IS the data. Protection is just a flag "require password to VIEW". 
            # It's not encrypted in storage (unless we implemented encryption in save).
            # The user's original code didn't encrypt the data field itself, just checked password on retrieval.
            # BUT save_chain in original code didn't encrypt data field either.
            # For this UI, let's respect the "Protected" flag if possible.
            
            # We need to look up the actual block to see if it's protected
            # because final_data is just the compiled dictionary.
            # Use self.blockchain.chain[index].is_protected
            
            # Limitation: Correction blocks update the data. 
            # If original was protected, is the correction protected? 
            # Let's assume protection is property of the original block index for now.
            
            original_block = self.blockchain.chain[index]
            is_protected = original_block.is_protected
            
            title_text = data.get("title", "Untitled")
            if is_protected:
                title_text = "🔒 " + title_text
            
            btn = ctk.CTkButton(
                self.scrollable_frame, 
                text=f"#{index} {title_text}", 
                command=lambda i=index: self.load_note(i),
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "#DCE4EE"),
                hover_color=("gray70", "gray30")
            )
            btn.pack(fill="x", pady=2)

    def load_note(self, index):
        # Check protection
        original_block = self.blockchain.chain[index]
        if original_block.is_protected:
            pwd = ctk.CTkInputDialog(text=f"Enter password for Note #{index}:", title="Protected Note").get_input()
            # Verify using blockchain method (which hashes input and compares)
            # We need to manually duplicate the check here or expose a "check_password" method
            # Reusing get_block_data logic
            check = self.blockchain.get_block_data(index, pwd)
            if check == "❌ INCORRECT PASSWORD" or check == "🔒 PROTECTED — password required":
                messagebox.showerror("Error", "Incorrect Password")
                return
        
        # Load data (use final data to get latest version)
        final_data = self.blockchain.get_final_data()
        data = final_data.get(index)
        
        if data:
            self.current_block_index = index
            self.title_entry.delete(0, "end")
            self.title_entry.insert(0, data.get("title", ""))
            
            self.content_text.delete("0.0", "end")
            self.content_text.insert("0.0", data.get("content", ""))
            
            self.status_label.configure(text=f"Editing Block #{index}")
            
            # Update switch
            self.is_protected_var.set(1 if original_block.is_protected else 0)

    def verify_chain_action(self):
        is_valid = self.blockchain.is_valid()
        if is_valid:
            messagebox.showinfo("Blockchain Verified", "✅ The Blockchain integrity is verified and secure.")
        else:
            messagebox.showerror("Blockchain Error", "❌ The Blockchain is INVALID! References or Hashes do not match.")

