import time
import json
import hmac
import hashlib
import datetime

PRIVATE_KEY = b"my-very-secret-private-key"

def signaturedata(message: str) -> str:
    signature = hmac.new(
        PRIVATE_KEY,
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return signature

def verify_message(message: str, signature: str) -> bool:
    expected = hmac.new(PRIVATE_KEY, message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

class Block:
    def __init__(self, index, timestamp, data, previous_hash,signature):
        self.index = index
        self.timestamp = timestamp
        self.data = data
        self.previous_hash = previous_hash
        self.hash = self.create_hash()
        self.signature = signature
    def create_hash(self):
        data_text = (
            json.dumps(self.data, sort_keys=True)
            if isinstance(self.data, dict)
            else str(self.data)
        )

        block_string = f"{self.index}{self.timestamp}{data_text}{self.previous_hash}"
        return hashlib.sha256(block_string.encode()).hexdigest()


class Blockchain:
    def __init__(self):
        self.chain = []
        self.create_genesisb()

    def create_genesisblock(self):
        ts = time.time()
        sig = signaturedata(f"0|{ts}|Genesis Block|0")
        self.chain.append(Block(0, ts, "Genesis Block", "0", sig))
       

    def add_block(self, data):
        last_block = self.chain[-1]

        index = last_block.index + 1
        timestamp = time.time()
        previous_hash = last_block.hash
        data_txt = (
        json.dumps(data, sort_keys=True)
        if isinstance(data, dict)
        else str(data)
    )   
        message_to_sign = f"{index}|{timestamp}|{data_txt}|{previous_hash}"
        signature = signaturedata(message_to_sign)



        new_block = Block(
            index=index,
            timestamp=timestamp,
            data=data,
            previous_hash=previous_hash,
            signature=signature,
        )
        self.chain.append(new_block)
    def add_correction_block(self, block_index, corrected_data):
            
      correction_info = {
            "correction_of": block_index,
            "corrected_data": corrected_data,
            "note": "This block corrects a previous incorrect entry."
        }

      last = self.chain[-1]

         
      index=last.index + 1
      timestamp=time.time()
      previous_hash=last.hash
      data_string = json.dumps(correction_info, sort_keys=True)
      message_to_sign = f"{index}|{timestamp}|{data_string}|{previous_hash}"
      signature = signaturedata(message_to_sign)
     
      correction_block = Block(
          index=index,
          timestamp=timestamp,
          data=correction_info,
          previous_hash=previous_hash,
          signature=signature
    )
      self.chain.append(correction_block)
      print(f" Correction block added for block #{block_index}")
    
    def get_final_data(self):
        final = {}

  
        final.update({
          block.index: block.data
          for block in self.chain
          if not (isinstance(block.data, dict) and "correction_of" in block.data)
    })

   
        final.update({
          block.data["correction_of"]: block.data["corrected_data"]
          for block in self.chain
          if (isinstance(block.data, dict) and "correction_of" in block.data)
    })

        return final
    def is_valid(self):
        for prev, curr in zip(self.chain, self.chain[1:]):

          if curr.hash != curr.calculate_hash():
            return False

          if curr.previous_hash != prev.hash:
            return False

          data_string = (
            json.dumps(curr.data, sort_keys=True)
            if isinstance(curr.data, dict) else str(curr.data)
        )
          message = f"{curr.index}|{curr.timestamp}|{data_string}|{curr.previous_hash}"

          if not verify_message(message, curr.signature):
                return False
            
        return True
    
    def save_chain(self, filename="current_chain.json"):
        
        if filename is None:
           timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
           filename = f"chain_{timestamp}.json"

        export = [
            {
                "index": b.index,
                "timestamp": b.timestamp,
                "data": b.data,
                "previous_hash": b.previous_hash,
                "hash": b.hash,
                "signature": b.signature
            }
            for b in self.chain
        ]

        with open(filename, "w") as f:
            json.dump(export, f, indent=4)
        print(f"Blockchain saved to {filename}")
    
    @staticmethod
    def load_chain(filename):
        
        try:
            with open(filename, "r") as f:
                raw = json.load(f)

            blockchain = Blockchain()
            blockchain.chain = []

            for block_data in raw:
                block = Block(
                    index=block_data["index"],
                    timestamp=block_data["timestamp"],
                    data=block_data["data"],
                    previous_hash=block_data["previous_hash"],
                    signature=block_data["signature"]
                )
                blockchain.chain.append(block)

            print(f" Loaded blockchain from {filename}")
            return blockchain

        except FileNotFoundError:
            print(" File not found.")
            return None