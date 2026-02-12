import os
from healthchain import Blockchain
from token_system import TokenSystem
from security import get_current_device_id
from project_manager import (
    list_projects, get_last_project, set_last_project,
    create_project, get_project_info, project_exists, save_project_metadata
)

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def wait():
    input("\nPress ENTER to continue...")

def control_health_data(data):
    """Validates health data input"""
    if not data or data.strip() == "":
        return False
    # Accept any non-empty string as valid health data
    return True

def validate_blockindex(index_input, chain_length):
    """Validates block index input"""
    try:
        index = int(index_input)
        if 0 <= index < chain_length:
            return index
        return None
    except ValueError:
        return None

# ----------------------------------------------
# SIMPLE PROJECT MENU (Your desired version)
# ----------------------------------------------

blockchain = None
tokens = None
project_name = None
encryption_password = None

while True:
    clear_screen()
    print("🔐 Health Blockchain System")
    print("📱 Device:", get_current_device_id())
    print("==============================\n")

    print("1 - Create new blockchain project")
    print("2 - Open existing project")
    print("3 - Exit\n")

    choice = input("Select: ")

    # -------------------------------
    # CREATE NEW PROJECT
    # -------------------------------
    if choice == "1":
        project_name = input("Project name: ").strip()

        if not project_name:
            print("❌ Project name cannot be empty!")
            wait()
            continue

        if project_exists(project_name):
            print("❌ A project with this name already exists.")
            wait()
            continue

        create_project(project_name)
        set_last_project(project_name)

        use_encryption = input("Encrypt blockchain? (y/n): ").lower() == "y"
        if use_encryption:
            encryption_password = input("Set password: ")
        else:
            encryption_password = None

        save_project_metadata(project_name, encrypted=use_encryption)

        blockchain = Blockchain(
            encryption_password=encryption_password,
            project_name=project_name
        )

        tokens = TokenSystem(user=project_name)
        tokens.add_tokens(1)

        print(f"✅ Project '{project_name}' created.")
        print("💰 Token +1 (genesis block reward).")
        break

    # -------------------------------
    # OPEN EXISTING PROJECT
    # -------------------------------
    elif choice == "2":
        projects = list_projects()
        if not projects:
            print("❌ No projects found.")
            wait()
            continue

        print("\nAvailable Projects:\n")
        for i, p in enumerate(projects, 1):
            print(f"{i}. {p['name']}")

        try:
            sel = int(input("\nSelect number: "))
            project_name = projects[sel - 1]["name"]
        except:
            print("❌ Invalid selection.")
            wait()
            continue

        info = get_project_info(project_name)

        password = None
        if info["encrypted"]:
            password = input("Enter password: ")

        blockchain = Blockchain.load_chain(
            filename=info["path"],
            encryption_password=password,
            project_name=project_name
        )

        if not blockchain:
            print("❌ Failed to load project.")
            wait()
            continue

        tokens = TokenSystem(user=project_name)

        print(f"✅ Loaded project '{project_name}'")
        break

    # -------------------------------
    # EXIT
    # -------------------------------
    elif choice == "3":
        exit()

    else:
        print("❌ Invalid option.")
        wait()


# Initialize token system with project
tokens = TokenSystem(user="Kadircan", project_name=project_name)

# Main menu
def menu():
    print("\n🔐 Health Blockchain System")
    if project_name:
        print(f"📁 Project: {project_name}")
    print(f"📱 Device ID: {get_current_device_id()}")
    if blockchain.encryption_password:
        print("🔒 Encrypted mode active")
    print("\n1 - Add health data")
    print("2 - Show blockchain")
    print("3 - Verify blockchain")
    print("4 - Show token balance")
    print("5 - Correct previous health data")   
    print("6 - Show final corrected health data")
    print("7 - Save blockchain (auto-saving enabled)")
    print("8 - Exit")

while True:
    clear_screen()
    menu()
    choice = input("Select an option ")

    if choice == "1":
        # Check if user has tokens
        if not tokens.has_tokens():
            print("❌ You don't have any tokens!")
            print(f"💰 Current balance: {tokens.get_balance()}")
            print("⚠️  You need at least 1 token to add a block.")
            wait()
            continue
        
        print("\nEnter Health Data:")
        print("Type '0' or write 'exit' to return to the main menu")
        data = input("")

        if data in ("q", "quit", "exit", "0", "back"):
               print("Returning to main menu.")
               continue
        if not control_health_data(data):
               print("❌ Invalid health data")
               wait()
               continue

        # Ask if block should be protected
        protect = input("🔒 Make this block protected (password required to read)? (y/n): ").lower() == 'y'
        protection_password = None
        if protect:
            protection_password = input("Set protection password: ")
            if not protection_password:
                print("⚠️  Password cannot be empty. Block will not be protected.")
                protect = False

        # Spend token first
        if not tokens.spend_tokens(1):
            print("❌ Failed to spend token. Operation cancelled.")
            wait()
            continue

        # Add block
        blockchain.add_block(data, is_protected=protect, protection_password=protection_password)
        
        # Award token after successful block addition
        tokens.add_tokens(1)
        
        # Auto-save
        blockchain.save_chain(encrypted=bool(blockchain.encryption_password))

        print("✅ Health data added and token awarded (+1)")
        if protect:
            print("🔒 Block is protected with password")
        print("💾 Auto-saved")
        wait()
        continue
                

    elif choice == "2":
        print(f"\n📋 Blockchain ({len(blockchain.chain)} blocks):\n")
        for block in blockchain.chain:
            is_protected = getattr(block, 'is_protected', False)
            protection_icon = "🔒" if is_protected else "📄"
            
            print(f"{protection_icon} Block {block.index}: ", end="")
            
            if is_protected:
                password = input(f"  [Protected - Enter password to view, or press Enter to skip]: ")
                if password:
                    data = blockchain.get_block_data(block.index, password)
                    print(f"  Data: {data}")
                else:
                    print("  Data: [PROTECTED - Password required]")
            else:
                print(f"{block.data}")
            
            print(f"  Hash: {block.hash[:20]}...")
            print(f"  Device: {getattr(block, 'device_id', 'N/A')[:8]}...")
            print()
  
        wait()
    elif choice == "3":
        print("\n🔍 Verifying blockchain...")
        is_valid = blockchain.is_valid()
        if is_valid:
            print("✅ Blockchain valid: True")
            print(f"📱 Device ID matches: {blockchain.device_id == get_current_device_id()}")
        else:
            print("❌ Blockchain valid: False")
            print("⚠️  Blockchain integrity may be compromised or belongs to another device!")
        
        wait()
    elif choice == "4":
        print(f"\n💰 Token balance: {tokens.get_balance()}")
        wait()
   
   
    elif choice == "5":
        index_input = input("Which block index is wrong: ")
        block_index = validate_blockindex(index_input, len(blockchain.chain))

        if block_index is None:
            print("❌ Invalid index")
            wait()
            continue

        value = input("Enter corrected data: ")
        valid = control_health_data(value)

        if valid:
              blockchain.add_correction_block(block_index, value)
              print("✅ Correction applied.")
              # Auto-save
              blockchain.save_chain(encrypted=bool(blockchain.encryption_password))
              print("💾 Auto-saved")
        else:
             print("❌ Invalid correction.")
    
        wait()
        continue

    elif choice == "6":
        print("\n📊 Final Corrected Health Data")
        print("="*50)
        final_data = blockchain.get_final_data()
        for index, data in sorted(final_data.items()):
            print(f"Block {index}: {data}")   
        wait()
            
    elif choice == "7":
       print("💾 Saving blockchain...")
       blockchain.save_chain(encrypted=bool(blockchain.encryption_password))
       print("✅ Blockchain saved successfully")
       wait()
       
    elif choice == "8":
       print("💾 Saving blockchain and exiting...")
       blockchain.save_chain(encrypted=bool(blockchain.encryption_password))
       set_last_project(project_name)  # Save last project
       print("✅ Goodbye!")
       break

    else:
        print("❌ Invalid choice")
        wait()
