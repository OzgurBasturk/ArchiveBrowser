#!/bin/bash
# Description : Archive Browser Launcher

# 1. Setup Environment
export TERM=linux
export XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}

# 2. Clear Screen
printf "\033c" > /dev/tty0
printf "\033c"

# 3. Move to script dir
cd "$(dirname "$0")"

# 4. Enter the App Folder
if [ -d "ArchiveApp" ]; then
    cd ArchiveApp
fi

# 5. Run the Python Tool
python3 ArchiveDownloader.py 2> launch_error.txt

# 6. Clean exit
printf "\033c"