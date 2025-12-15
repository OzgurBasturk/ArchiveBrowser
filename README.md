# ArchiveBrowser for R36S / ArkOS

ArchiveBrowser is a lightweight, Python-based download manager designed for the R36S and similar retro handhelds. It allows you to browse, search, and download files directly from Internet Archive collections to your device's storage without needing a computer.

📱 Compatibility

This tool has been tested on the R36S Plus. It is designed to work on most Linux-based retro handhelds that support Python 3.

    R36S: Requires a USB-C Wi-Fi Dongle (OTG).

    R36S Plus: Works natively (built-in Wi-Fi).

    R36XX: Should Work natively (built-in Wi-Fi).

    ArkOS Devices: Generally compatible with any device running ArkOS and has a internet access.

    Note: An active internet connection is required to browse and download.

🌟 Features

    Direct Download: Downloads files directly to your specific console folders (/roms/videos, /roms/music, etc.).

    Searchable: Includes a built-in on-screen keyboard to filter huge file lists instantly.

    Smart Caching: Loads previously visited collections instantly (no waiting for re-scraping).

    Visible Progress and Cancel: Full download progress bar with speed (MB/s) and file size indicators. Can cancel during download.

    Configurable: Entirely driven by a JSON file—you choose the collections.

    Authenticated Access: Supports Archive.org API keys for faster download speeds.

⚠️ IMPORTANT: Editing Files

DO NOT use Windows Notepad. These scripts run on Linux. Windows uses different text formatting (CRLF) which breaks the code.

    Download Notepad++ (Free).

    Open the file.

    Go to Edit -> EOL Conversion -> Select Unix (LF).

    Save.

🚀 Installation

    Navigate to your roms/tools/ folder on your SD card.

    Create a new folder named ArchiveApp.

    Copy ArchiveDownloader.py and collections.json into that folder.

    Copy Archive_Browser.sh to /roms/tools/ to launch it from your main menu.

Folder Structure:

    /roms/tools/
    ├── Archive_Browser.sh
    └── ArchiveApp/
        ├── ArchiveDownloader.py
        ├── collections.json
        └── keys.txt (Optional)

⚙️ Configuration (collections.json)

The tool comes with Public Domain examples. To add your own collections, edit collections.json using Notepad++.

Entry Format:
JSON

    {
      "name": "My HTML Method Collection Name",
      "method": "HTML", 
      "url": "https://archive.org/download/IDENTIFIER/filename.zip/",
      "filter": "",
      "folder": "destination_folder",
      "extension": ".zip"
    },
    {
      "name": "My API Method Collection Name",
      "method": "API", 
      "url": "IDENTIFIER",
      "filter": "",
      "folder": "destination_folder",
      "extension": ".zip"
    }

Field Explanations:

    name: The title displayed in the app menu.

    method:

        "HTML": Scrapes the directory listing directly. Best for direct download links (e.g., links ending in / or .zip/). Fast and reliable for "View Contents".

        "API": Queries the Archive.org database. Useful for massive collections that aren't inside a zip file.

    url: For HTML method it is the direct link to the directory. For API method it is just the identifier part of the link.

    filter: (Mainly for API method) Text entered here must exist in the filename for it to show up.

        Example: If a collection has 1,000 files but you only want the NASA versions, set "filter": "NASA".

        Leave as "" to show everything.

    folder: The folder inside /roms/ where files will be saved (e.g., videos, music).

    extension: The file extension to show (e.g., .mp3, .mp4, .wav).

🔑 Authentication (Optional)

For faster download speeds, you can use your Archive.org account credentials.

    Log into Archive.org.

    Go to archive.org/account/s3.php to get your keys.

    Create a file named keys.txt inside the ArchiveApp folder. Use Notepad++ as explained above when sawing your keys.txt.

    Paste your Access Key (Line 1) and Secret Key (Line 2).

🎮 Controls
Button	Function

    D-Pad	Navigate Lists
    A	Select / Download / Confirm
    B	Back / Cancel Download / Exit App
    X	Search (Opens Keyboard)
    Y	Refresh (Delete cache and re-scrape)
    Start	Confirm Search
    L1 / R1   Jump to Next/Prev Letter (Fast Scroll)

📝 Legal Disclaimer

ArchiveBrowser is a content-agnostic download client. It contains no copyrighted games, system files, or BIOS images. The included configuration file links strictly to Public Domain content for demonstration purposes. Users are responsible for ensuring they have the legal right to download any content they access using this tool.
