import vdf
import zlib
import shutil
from datetime import datetime
import os
from pathlib import Path


#global variables
shortcuts_file_backups_dir = "shortcuts_file_backups"
art_supported_file_type = (".png", ".jpg", ".jpeg")


# global function
def CleanPath(path):
    if path.startswith("\"") and path.endswith("\""):
        path = path[1:-1]
    return path
def CheckPath(path, CanBeEmpty, EmptyDefault, EndsWith):
    path = CleanPath(path)
    while True:

        if not path and CanBeEmpty:
            path = EmptyDefault
            break

        elif not path and not CanBeEmpty:
            path = input("Can't leave empty: ")
            path = CleanPath(path)

        elif not Path(path).exists():
            path = input("Path doesn't exist: ")
            path = CleanPath(path)

        elif not path.lower().endswith(EndsWith):
            path = input("make sure to input path of the file not it's directory: ")
            path = CleanPath(path)

        else:
            break 



print("""============================================================
    NON STEAM EMULATION 
    A tool that makes adding emulated games to steam easier
============================================================""")
print("""!!! MAKE SURE TO CLOSE STEAM BEFORE DOING ANYTHING !!!
============================================================""")



#input shortcuts.vdf file path
shortcuts_file_path = input("""- Input shortcuts.vdf file path
(C:\\Program Files (x86)\\Steam\\userdata\\[YOURSTEAMID]\\config\\shortcuts.vdf)
(leave empty if shortcuts.vdf is in the same dir as this script): """)

CheckPath(shortcuts_file_path, True, "shortcuts.vdf", "shortcuts.vdf")
shortcuts_file_path = CleanPath(shortcuts_file_path)



print("""============================================================
     ! shortcuts.vdf will be backedup in ./shortcuts_file_backups
============================================================""")



# Input steam grid folder path
game_art_path = input("""- Input steam's grid folder path
(C:\\Program Files (x86)\\Steam\\userdata\\[YOURSTEAMID]\\config\\grid)
(if left empty, game's art will be moved to ./game_art): """)

CheckPath(game_art_path, True, "game_art", "")
game_art_path = CleanPath(game_art_path)



# Input Game Info and paths
print("""============================================================
    Game info: 
============================================================""")

Game_name = input("- Input Game name: ")
while not Game_name:
    Game_name = input("Please input game name: ")

Emulator_path = input("""- Input Emulator's executable path
(example: \"C:\\emulators\\emu1.exe)\": """)
CheckPath(Emulator_path, False, "", ".exe")
Emulator_path = CleanPath(Emulator_path)

Game_path = input("- Game file (ISO / EBOOT.BIN / .wbfs / etc..): ")
CheckPath(Game_path, True, "", "")
Game_path = CleanPath(Game_path)

Emulator_start_in_path = Emulator_path.split("\\")
for part in Emulator_start_in_path:
    if ".exe" in part:
        Emulator_start_in_path.pop()
Emulator_start_in_path = "\\".join(Emulator_start_in_path) + "\\"



# Input Game Art paths
print("""============================================================
    Game Art: 
============================================================""")

Game_grid_path = input("""- Game grid art path
(leave empty to skip):""")
CheckPath(Game_grid_path, True, "", art_supported_file_type)
Game_grid_path = CleanPath(Game_grid_path)

Game_hero_path = input("""- Game hero art path
(leave empty to skip):""")
CheckPath(Game_grid_path, True, "", art_supported_file_type)
Game_hero_path = CleanPath(Game_hero_path)

Game_logo_path = input("""- Game logo art path
(leave empty to skip):""")
CheckPath(Game_grid_path, True, "", art_supported_file_type)
Game_logo_path = CleanPath(Game_logo_path)

Game_preview_path = input("""- Game preview art path
(leave empty to skip):""")
CheckPath(Game_grid_path, True, "", art_supported_file_type)
Game_preview_path = CleanPath(Game_preview_path)

Game_icon_path = input("""- Game icon art path (.ico)
(leave empty to skip):""")
CheckPath(Game_grid_path, True, "", art_supported_file_type + (".ico",))
Game_icon_path = CleanPath(Game_icon_path)



#create shortcuts.vdf backup just in case
os.makedirs(shortcuts_file_backups_dir, exist_ok=True)
shutil.copy(shortcuts_file_path, shortcuts_file_backups_dir)
now = datetime.now()
now = now.strftime("%Y-%m-%d-%H%M%S")
os.rename(f"{shortcuts_file_backups_dir}\\shortcuts.vdf", f"{shortcuts_file_backups_dir}\\shortcuts_backup_{now}.vdf")



#calculate appid and artid(game art)
combined_string = (Game_name + Emulator_path + "\0")
crc = zlib.crc32(combined_string.encode('cp1252'))
art_id = crc | 0x80000000
app_id = art_id
app_id -= 0x100000000



#adding game data to the file
new_game =  {'appid': app_id,
              'AppName': Game_name,
              'Exe': f"\"{Emulator_path}\" \"{Game_path}\"",
              'StartDir': Emulator_start_in_path,
              'icon': Game_icon_path,
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



# Creating Game art folder (or skip)
os.makedirs(game_art_path, exist_ok=True)
if Game_grid_path:
    shutil.copy(Game_grid_path, game_art_path)
    os.rename(f"{game_art_path}\\{os.path.basename(Game_grid_path)}", f"{game_art_path}\\{art_id}p.png")

if Game_hero_path:
    shutil.copy(Game_hero_path, game_art_path)
    os.rename(f"{game_art_path}\\{os.path.basename(Game_hero_path)}", f"{game_art_path}\\{art_id}_hero.png")

if Game_logo_path:
    shutil.copy(Game_logo_path, game_art_path)
    os.rename(f"{game_art_path}\\{os.path.basename(Game_logo_path)}", f"{game_art_path}\\{art_id}_logo.png")

if Game_preview_path:
    shutil.copy(Game_preview_path, game_art_path)
    os.rename(f"{game_art_path}\\{os.path.basename(Game_preview_path)}", f"{game_art_path}\\{art_id}.png")



print("""============================================================
SUCCESS
============================================================""")
