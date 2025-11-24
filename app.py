import os
from healthchain import Blockchain
from token_system import TokenSystem

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def wait():
    input("\nPress ENTER to continue")
    

def control_health_data(data):
    data = data.strip()
   
    if not data:
        return False
  
    bad_characters = set("*/!@#$^&[]{}?|")
    if any(ch in bad_characters for ch in data):
        return False

    if data.isdigit():
        return False
  
    return True


def validate_blockindex(user_input, chain_length):
    
    if not user_input.isdigit():
        return None

    index = int(user_input)

    if index < 0 or index >= chain_length:
        return None

    return index


while True: 
    clear_screen()
    print("1 - Start new blockchain")
    print("2 - Load existing blockchain file")
    choice = input("Select option ")

    if choice == "1":
        blockchain = Blockchain()  
        print("New blockchain created")
        break
    elif choice == "2":
        filename = input("Enter filename to load: ")
        loaded = Blockchain.load_chain(filename)

        if loaded:
           blockchain = loaded
           break
        else:
            print(" Could not load file")
            continue

    else:
         print("Invalid selection.")
         continue

tokens = TokenSystem(user="Kadircan")




def menu():
    print("\n Health Blockchain System ")
    print("1 - Add health data")
    print("2 - Show blockchain")
    print("3 - Verify blockchain")
    print("4 - Show token balance")
    print("5 - Correct previous health data")   
    print("6 - Show final corrected health data")
    print("7 - Exit")

while True:
    clear_screen()
    menu()
    choice = input("Select an option ")

    if choice == "1":
        print("\nEnter Health Data:")
        print("Type '0' or write 'exit' to return to the main menu")
        data = input("")

        if data in ("q", "quit", "exit", "0", "back"):
               print("Returning to main menu.")
               continue
        if not control_health_data(data):
               print("Invalid health data")
               wait()
               continue

    
        blockchain.add_block(data)
        tokens.add_tokens()
        blockchain.save_chain()

        print("Health data added and token awarded")
        wait()
        continue
                

    elif choice == "2":
        for block in blockchain.chain:
            print(vars(block))
  
        wait()
    elif choice == "3":
        print("\nBlockchain valid:", blockchain.is_valid())
        
        wait()
    elif choice == "4":
        print("\nToken balance:", tokens.get_balance())
        wait()
   
   
    elif choice == "5":

        index_input = input("Which block index is wron ")
        block_index = validate_blockindex(index_input, len(blockchain.chain))

        if block_index is None:
            print(" Invalid index")
            wait()
            continue

        value = input("Enter corrected data: ")
        valid = control_health_data(value)

        if valid:
              blockchain.add_correction_block(block_index, value)
              print("Correction applied.")
              blockchain.save_chain()
        else:
             print("Invalid correction.")
    
        wait()
        continue

    elif choice == "6":
        print("\n Final Corrected Health Data ")
        final_data = blockchain.get_final_data()
        for index, data in final_data.items():
            print(f"Block {index}: {data}")   
        wait()
            
    elif choice == "7":
       print("Saving blockchain and exiting.")
       blockchain.save_chain()    
       break

    else:
        print("Invalid choice")
        wait()
 
