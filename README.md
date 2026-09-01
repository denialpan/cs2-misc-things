A simple python wrapper program to automate some things I find tedious to interop between. This handles the main 4 "modes" that the game can open in, while handling all the proper file operations to allow safe connections to VAC servers without erroring out after introducing/modifying game files.

**Main features**:
- Install [CS2Fixes](https://github.com/Source2ZE/CS2Fixes) locally on client.
- Swap between opening CS2 Workshop Tools or the vanilla game, with [CS2Fixes](https://github.com/Source2ZE/CS2Fixes) loaded for either.
- Auto joiner - auto connect to a CS2 server, primarily the [GFL Zombie Escape](https://gflclan.com/) server. Configurable.

**CLI arguments**:
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

**Requirements**:
- Tested only on Windows
- [PySide6](https://pypi.org/project/PySide6/)
- [python-a2s](https://pypi.org/project/python-a2s/)

**Credits**:
Guide to offline ZE maps: <https://www.youtube.com/watch?v=lJW8SSoDsbo>
