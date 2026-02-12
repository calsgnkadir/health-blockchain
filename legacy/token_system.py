import json
import os

class TokenSystem:
    def __init__(self, user="default_user", project_name=None):
        self.user = user
        self.project_name = project_name
        self.tokens = {}
        self.load_tokens()

    def load_tokens(self):
        tokens_file = "tokens.json"
        if self.project_name:
            from project_manager import get_tokens_file
            tokens_file = get_tokens_file(self.project_name)
        
        if os.path.exists(tokens_file):
            try:
                with open(tokens_file, "r", encoding="utf-8") as file:
                    self.tokens = json.load(file)
            except (json.JSONDecodeError, IOError):
                print("Warning: tokens.json is corrupted. Starting with empty tokens.")
                self.tokens = {}
        else:
            self.tokens = {}
       
        if self.user not in self.tokens:
            self.tokens[self.user] = 5
            self.save_tokens()

    def save_tokens(self):
        tokens_file = "tokens.json"
        if self.project_name:
            from project_manager import get_tokens_file
            tokens_file = get_tokens_file(self.project_name)
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(tokens_file), exist_ok=True)
        
        try:
            with open(tokens_file, "w", encoding="utf-8") as f:
                json.dump(self.tokens, f, indent=4)
        except IOError as e:
            print(f"Error saving tokens: {e}")

    def add_tokens(self, amount=1):
        current = self.tokens.get(self.user, 0)
        self.tokens[self.user] = current + amount
        self.save_tokens()

    def get_balance(self):
        return self.tokens.get(self.user, 0)
    
    def has_tokens(self, required=1):
        """Check if user has enough tokens"""
        return self.get_balance() >= required
    
    def spend_tokens(self, amount=1):
        """Spend tokens (for adding blocks)"""
        if not self.has_tokens(amount):
            return False
        current = self.tokens.get(self.user, 0)
        self.tokens[self.user] = current - amount
        self.save_tokens()
        return True
