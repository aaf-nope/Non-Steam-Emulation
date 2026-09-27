# initial scipt that I started working with
# This script was made for testing purposes only

import vdf
import os
import linecache

total_games = 0
data_text_file = "LegacyScripts/data.txt"
game_data_folder_path = "LegacyScripts/GamesData"

# read vdf file in binary and store it as d
with open("shortcuts.vdf", "rb") as f:
    d = vdf.binary_load(f)

# dump the content of d in a text file txt in readable format 
with open(data_text_file, "w") as t:
    t.write(vdf.dumps(d, pretty=True))
    print("vdf files is printed")


# This code block was made to count the amount of games and write down each game's data in a single file

with open(data_text_file, "r") as t:
    # amount of lines in the vdf file
    total_lines = len(t.readlines())

    i = 3 # starting line with the first game
    while i < total_lines:

        # create folder games_data if inexistent and create a file for each game then insert its data in it
        os.makedirs(game_data_folder_path, exist_ok=True)

        with open(f"{game_data_folder_path}/{total_games}", "w") as f:
                for j in range(i, i+23):
                    f.write(linecache.getline(data_text_file, j))

        total_games += 1 # +1 the total amount of games
        i += 23 # jump 23 lines which is the amount of lines of data for each game

    print("amount of games is", total_games)
