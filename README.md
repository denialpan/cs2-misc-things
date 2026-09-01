A simple python wrapper to automate some things I find tedious to interop. This handles the main 4 "modes" that the game can open in, while handling all the proper file operations to allow safe connections to VAC servers without erroring out after introducing/modifying game files.

<img width="867" height="704" alt="cs2miscthings" src="https://github.com/user-attachments/assets/f3f6ef3c-d27f-4b00-8211-1734316e0d6a" />

### Main features
- Streamline installing [CS2Fixes](https://github.com/Source2ZE/CS2Fixes) locally for client (not server).
- Swap between opening CS2 Workshop Tools or the vanilla game, with [CS2Fixes](https://github.com/Source2ZE/CS2Fixes) loaded for either.
- Auto joiner - auto connect to a CS2 server, primarily the [GFL Zombie Escape](https://gflclan.com/) server. Configurable.

### CLI arguments
```
  -h, --help   show this help message and exit
  -gui         launch gui
  -tools       launch workshop tools
  -cs2fixes    launch with cs2fixes
  -autojoiner  run autojoiner
  -ip IP       autojoiner server IP
  -port PORT   autojoiner server port
  -name NAME   autojoiner player name to check for
```

### Requirements
- Tested only on Windows
- See [requirements.txt](https://github.com/denialpan/cs2-misc-things/blob/main/requirements.txt)
- Metamod: https://www.metamodsource.net/
- Metamod Launcher: https://github.com/Poggicek/metamod-launcher
- CS2Fixes: https://github.com/Source2ZE/CS2Fixes
- StripperCS2: https://github.com/Source2ZE/StripperCS2/
- GFL CS2 ZE Configs: https://github.com/gflze/CS2-ZE-Configs/
- admins.jsonc: https://pastebin.com/Ha83AvNw
- cs2fixes.cfg: https://pastebin.com/NUNWgZAY

### Credits
Guide to offline ZE maps: <https://www.youtube.com/watch?v=lJW8SSoDsbo>
