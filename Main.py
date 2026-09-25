import vdf
import zlib
import shutil
from datetime import datetime
import os

#global variables
shortcuts_file_path = "shortcuts.vdf"
shortcuts_file_backups_dir = "shortcuts_file_backups"

print("====================")
print("Add Emulated Games to Steam")
print("====================")

# Extracted Game Info
Game_name = input("Game name: ")
Console = input("Emulated console: ")
Emulator = input("Emulator name: ")
Emulator_path = input("Emulator's executable path (example: \"C:\\emulators\\emu1.exe)\": ")
if Emulator_path.startswith("\"") and Emulator_path.endswith("\""):
    Emulator_path = Emulator_path[1:-1]
Game_path = input("Game file (ISO / EBOOT.BIN / .wbfs / etc..): ")
Emulator_start_in_path = Emulator_path.split("\\")
for part in Emulator_start_in_path:
    if ".exe" in part:
        Emulator_start_in_path.pop()
Emulator_start_in_path = "\\".join(Emulator_start_in_path) + "\\"


#calculate appid and artid(game art)
combined_string = (Game_name + Emulator_path + "\0")
crc = zlib.crc32(combined_string.encode('cp1252'))
art_id = crc | 0x80000000
app_id = art_id
app_id -= 0x100000000


#create shortcuts.vdf backup just in case
os.makedirs(shortcuts_file_backups_dir, exist_ok=True)
shutil.copy(shortcuts_file_path, shortcuts_file_backups_dir)
now = datetime.now()
now = now.strftime("%Y-%m-%d-%H%M%S")
os.rename(f"{shortcuts_file_backups_dir}\\shortcuts.vdf", f"{shortcuts_file_backups_dir}\\shortcuts_backup_{now}.vdf")


#addiing game data to the file
new_game =  {'appid': app_id,
              'AppName': Game_name,
              'Exe': f"{Emulator_path} {Game_path}",
              'StartDir': Emulator_start_in_path,
              'icon': '',
              'ShortcutPath': '',
              'LaunchOptions': '',
              'IsHidden': 0,
              'AllowDesktopConfig': 1,
              'AllowOverlay': 1,
              'OpenVR': 0,
              'Devkit': 0,
              'DevkitGameID': '',
              'DevkitOverrideAppID': 0,
              'LastPlayTime': 0,
              'FlatpakAppID': '',
              'sortas': '',
              'tags': {}}

with open(shortcuts_file_path, "rb") as f:
    root = vdf.binary_load(f)
    root['shortcuts'][str(len(root['shortcuts']))] = new_game
    root['shortcuts'] = root['shortcuts']

with open(shortcuts_file_path, "wb") as f:
    vdf.binary_dump(root, f)

