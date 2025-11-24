import json
import os
class TokenSystem:
    def __init__(self, user="default_user"):
        self.user = user
        self.tokens = {}
        self.load_tokens()

    def load_tokens(self):
        if os.path.exists("tokens.json"):
            with open("tokens.json", "r", encoding="utf-8") as file:
              self.tokens = json.load(file)
        else:
       
            self.tokens = {}
       
        if self.user not in self.tokens:
            self.tokens[self.user] = 0
            self.save_tokens()

    def save_tokens(self):

        with open("tokens.json", "w") as f:
            json.dump(self.tokens, f, indent=4)

    def add_tokens(self, amount=1):
 
        current = self.tokens.get(self.user, 0)
        self.tokens[self.user] = current + amount

        self.save_tokens()

    def get_balance(self):
        return self.tokens[self.user]
