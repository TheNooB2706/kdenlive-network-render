# kdenlive-network-render
A tool that lets you distribute your Kdenlive render to multiple computers. Currently available for linux only.

# Table of contents
- [Project Title](#kdenlive-network-render)
- [Table of contents](#table-of-contents)
- [Setup](#setup)
- [Usage](#usage)
- [Development](#development)
- [Contribute](#contribute)
    - [Porting to Windows](#porting-to-windows)
    - [Adding new features or fixing bugs](#adding-new-features-or-fixing-bugs)
- [License](#license)
- [Footer](#footer)

# Setup
[(Back to top)](#table-of-contents)
### Requirements:
* python3
* ssh
* sshfs
* ffmpeg
* rsync
* xvfb (for headless clients)
* melt

On Debian/Ubuntu:
```
sudo apt install python3 ssh sshfs ffmpeg rsync xvfb
```
_*Most of them should be installed by default, but I will just leave them in the command for those who use minimal installation._

#### Getting melt:
While you can install melt from the distro's repository, however it is most likely outdated. You can either:
1. Build from source
2. Modifying the kdenlive appimage into melt appimage

For building from source, refer to [melt Github repository](https://github.com/mltframework/mlt/).

#### Modifying kdenlive appimage into melt 

1. First, get [appimagetool](https://appimage.github.io/appimagetool/). This will be used to repackage the appimage.
1. Get Kdenlive appimage from the [official download website](https://kdenlive.org/en/download/).
1. Extract Kdenlive appimage. This will create a folder named "squashfs-root" in the current working directory.
```
./kdenlive-XXX.appimage --appimage-extract
```
1. Modify the "AppRun" file in the "squashfs-root" directory.

 Change the last line from:
 ```
 kdenlive --config kdenlive-appimagerc $@
 ```
 to:
 ```
 melt $@
 ```
1. Delete the file `org.kde.kdenlive.appdata.xml` in `squashfs-root/usr/share/metainfo`. This file prevent appimage from being built (as it is being modified)
1. (Optional) You can also remove unnecessary binaries or files unrelated to melt, but I skipped this because this could break the whole thing if wrong files are deleted. (And I have enough storage)
1. Rebuild the appimage
```
./appimagetool-XXX.appimage squashfs-root melt.appimage
```
 Or if you want compression (Command below use xz algorithm):
```
./appimagetool-XXX.appimage --comp xz squashfs-root melt.appimage
```
1. Finally move the created appimage to any convenient place to your liking.

#### Setting up ssh

Since this program use sshfs, you will need to setup ssh so that clients can connect to the server. If public/private key authentication is used, make sure the keys are set up correctly. Search Internet for tutorial.

#### Getting the program
You may clone this repository, or download from the [release page](https://github.com/TheNooB2706/kdenlive-network-render/releases). The latter is preferred as there will be no risk for you to download broken program (In case I commit something bad to the master branch). Save the script to convenient place. No additional python library is needed as only standard libraries are used.

# Usage
[(Back to top)](#table-of-contents)
## Prerequisite
### Setting up your project
In order for the generated .mlt file to work with this program, all the assets used in a kdenlive project must be accessible from the root directory. When you start a new project, make sure to save the .kdenlive file at a set root directory. Then, all of the media files must be within that directory or subdirectory of that directory. Take the example below:
```
Videos/
    myproject/
        project.kdenlive
        image1.jpg
        video1.mp4
        even more videos/
            video2.mp4
        background music/
            music.mp3
```
In the above example, the root directory is `Videos/myproject`. The .kdenlive file, `project.kdenlive` is saved at the root directory. All the other media files must be contained under the root directory.

Let's say you have an existing project you want to render, but the media files is all over the places:
```
user/
    Videos/
        myproject/
            project.kdenlive
            image1.jpg
        video1.mp3
    Music/
        bgmusic.mp3
    Pictures/
        Screenshot1234.jpg
```
The solution to this is to save the project file to the highest directory level such that all the media are within the root directory. Open the file `project.kdenlive` and resave it to `user/name.kdenlive`:
```
user/
    name.kdenlive
    Videos/
        myproject/
            project.kdenlive
            image1.jpg
        video1.mp3
    Music/
        bgmusic.mp3
    Pictures/
        Screenshot1234.jpg
```
Now the root of the project becomes `user/` and all the media files are within the root directory.

Then you can proceed to generate the .mlt file.

### Generating the .mlt file
Open your project file and press render:

![](https://i.ibb.co/34K2ccf/Screenshot-20210507-154613.png)

Customise the render setting to your liking, then press `Generate script`:

![](https://i.ibb.co/Ph8RGLn/Screenshot-20210507-154845.png)

Choose the name of the script to be generated and press `OK`:

![](https://i.ibb.co/x83Sk7Y/Screenshot-20210507-155058.png)

The .mlt file will be saved to `~/Videos/kdenlive-renderqueue`.

## Usage
It should be pretty clear that, `client.py` is the client program, while `server.py` is the server program. Server will be responsible to distribute job to client, while client will render the job given.

Continue from the prerequisite above, now you want to render the project at `~/Videos/kdenlive-renderqueue/projectfile.mlt`, first start the server:
```
#Assuming current working directory contains 'server.py' and 'client.py'
python3 server.py 12345 ~/Videos/kdenlive-renderqueue/projectfile.mlt
```
Where `12345` is the port of the server (you can choose any empty port you want, just make sure to note this down for client).

If you are using the appimage modification method to get melt, chances are it will not be located in `/usr/bin`. Specify the melt binary using `-b` option:
```
python3 server.py -b ~/path/to/melt/melt.appimage 12345 ~/Videos/kdenlive-renderqueue/projectfile.mlt
```

Then on the client side:
```
python3 client.py 192.168.1.23 12345
```
Where `192.168.1.23` is the IP address of the server (can be found using `ip a`) and `12345` is the port when you start the server.

Similarly, if you used the appimage modification method, the path to melt binary can be specified with the same option:
```
python3 client.py -b ~/path/to/melt/melt.appimage 192.168.1.23 12345
```

According to a [video](https://www.youtube.com/watch?v=I6HlcopF2rM) by [Mark Furneaux 2](https://www.youtube.com/channel/UCN3Dgu6CVBcecDkc5DmIIqw) (and also my personal experience when rendering on a really old hardware), parallel processing sometimes does not operate correctly. This is control by the `real_time` option in the .mlt file ([melt documentation](https://www.mltframework.org/faq/#does-mlt-take-advantage-of-multiple-cores-or-how-do-i-enable-parallel-processing)). In this case, you might want to set the value to `-1` (which means no parallel processing and no frame drop) with the option `-r` at client side:

```
python3 client.py -b ~/path/to/melt/melt.appimage -r "-1" 192.168.1.23 12345
```

If you also want to use the same computer that host the server to render, you can start the client as local mode with the option `-l`:
```
python3 client.py -b ~/path/to/melt/melt.appimage -l 192.168.1.23 12345
```

Repeat this for as many clients as you want. After all the clients are connected, press `CTRL+C` on server side:
```
Server listening on port 12345. Press Ctrl+C when all clients are connected.
client1 from ('127.0.0.1', 41176) connected.
^C
-------------------------------
Stopped accepting connections. Initialising.
Pinging client1 ......
client1 ready.
-------------------------------
Total clients: 1
Clients list: 
  client1 from ('127.0.0.1', 41176)
-------------------------------
Press Enter to continue...
```
Then you can check if all the clients are there, press Enter, sit back and take a cup of coffee (if nothing goes wrong lol).

For more options' help, refer to the documentation below.

## Documentation
### server
#### Program help:
```
usage: server.py [-h] [-f FRAME_SPLIT] [-b MELT_BINARY] [--no-cleanup]
                 port mltfile

positional arguments:
  port                  Port of the server
  mltfile               Path to generated MLT project file.

optional arguments:
  -h, --help            show this help message and exit
  -f FRAME_SPLIT, --frame-split FRAME_SPLIT
                        Set the number of frames to split into for each jobs.
                        Default to 1000 frames.
  -b MELT_BINARY, --melt-binary MELT_BINARY
                        Path to the melt binary. Default to /bin/melt
  --no-cleanup          If this option is set, the temporary files and folders
                        created will not be deleted at exit.
```
#### Detailed explanation:
* `-f`, `--frame-split` [integer]  
 When distributing jobs, the server will segregates all the frames into chunks with number of frames `n` which can be set with this option. The default size of a job is 1000 frames. For example, you want to render a project with 1324 frames, with the default setting, this will be splitted into the following list of jobs:
 ```
 [0-999, 1000-1324]
 ```
 where each job consists of 1000 frames except the last one.
 
* `-b`, `--melt-binary` [path]  
 This option is used to set the path to melt binary. If you compile from source or installed from your distro repository, it will (probably, someone please confirm this) be installed to `/usr/bin`, which is (currently) the default value of this option.
 
* `--no-cleanup`  
 You probably will not want to use this option, but if you do, this will skip the deletion of temporary files created at `rootdir/.kdenlive_network_render`

### client
#### Program help:
```
usage: client.py [-h] [-b MELT_BINARY] [-d PROGRAM_DIR] [-l]
                 [-ssh SSH_COMMAND] [-t THREADS] [-r REAL_TIME] [-x]
                 [--no-cleanup]
                 address port

positional arguments:
  address               IP address of server
  port                  Port of the server

optional arguments:
  -h, --help            show this help message and exit
  -b MELT_BINARY, --melt-binary MELT_BINARY
                        Path to the melt binary. Default to /bin/melt
  -d PROGRAM_DIR, --program-dir PROGRAM_DIR
                        Path where this program use to store temporary files
                        and mountpoint. Default to ~/.kdenlive_network_render
  -l, --local           Start as local client where client and server are on
                        the same machine.
  -ssh SSH_COMMAND, --ssh-command SSH_COMMAND
                        Custom ssh command. Use for custom private key or ssh
                        port etc.
  -t THREADS, --threads THREADS
                        Value of threads option in the .mlt file. Default to
                        number of cpu cores.
  -r REAL_TIME, --real-time REAL_TIME
                        The value of real_time option in the .mlt file.
                        Default to -[number of cpu cores].
  -x, --use-xvfb        Use xvfb as fake x11 server. Useful on headless
                        server.
  --no-cleanup          If this option is set, the temporary files and folders
                        created will not be deleted at exit.
```
#### Detailed explanation:
* `-b`, `--melt-binary` [path]  
 This option is used to set the path to melt binary. If you compile from source or installed from your distro repository, it will (probably, someone please confirm this) be installed to `/usr/bin`, which is (currently) the default value of this option.

* `-d`, `--program-dir` [path]  
 When the program launch, it will create a directory `.kdenlive_network_render` at `~` by default. All the jobs rendered will be temporarily saved to that folder before being uploaded back to server. This option will be useful when `~` does not have enough space, to set the temporary directory to other place. Keep in mind that the program will use `sshfs` to mount the server root directory in this directory, I'm not sure if `sshfs` will mount on non linux filesystem, so take note. If this doesn't work (someone open an issue), I may change this behaviour in future.

* `-l`, `--local`  
 This option can be used when you want to start a client on the same machine as the server. When set, it will not use `sshfs` to mount the root directory, since now it has access to the directory directly.
 
* `-ssh`, `--ssh-command`  
 You can specify custom ssh command with this option. Value will be forwarded to `sshfs -o ssh_command="{}"` in `sshfs` and `rsync -e "{}"` in rsync (opportunity for code injection huh?). In this way, custom ssh port or private key can be used. (Make sure to enclosed the command with quotes)
 
* `-t`, `--threads` [integer]  
 This controls the `threads` option in the .mlt file. According to a [reddit post](https://www.reddit.com/r/kdenlive/comments/ka0aak/kdenlive_gpucpu_use_threads_mlt_and_ffmpeg_tips/), this option control the number of threads created by `ffmpeg` when rendering. Default to number of cpu cores with `os.cpu_count()`.
 
* `-r`, `--real-time` [integer]  
 This controls the `real_time` option in the .mlt file. This is the number of threads created by `melt` itself. Default to `-[cpu count]` where cpu count is retrieved with `os.cpu_count()`.
 
* `-x`, `--use-xvfb`  
 Some effects of melt need X server to run, so if client is headless (no GUI), this option can be set to use xvfb as fake X server. Otherwise, you will get messed up video. What this option does is add `xvfb-run -a` to the front of usual melt command.
 
* `--no-cleanup`  
 Same as server, if this is set, temporary file (at `--program-dir`) will not be deleted on exit.
 
# Development
[(Back to top)](#table-of-contents)

Under construction

# Contribute
[(Back to top)](#table-of-contents)
### Porting to Windows
As you may have noticed, currently there are no Windows version available. That is because this program depends on Linux utilities such as ssh, sshfs and rsync (and I use Linux). Luckily it is not completely impossible to port it as those utilities are available on Windows as well, but the behaviour may not be the same (take [sshfs-win](https://github.com/billziss-gh/sshfs-win) for example). I have planned to do this in the future (so I can borrow my friend's computer for rendering), but this will take some time. So if anyone would like to contribute Windows version, that would be really nice. Ideally, Linux server/client should be compatible with Windows client/server, but anything starts from somewhere, so you could start with an incompatible version first, then make it compatible.

For end users who want to use this program on Windows, your best bet now is probably to use WSL.

### Adding new features or fixing bugs
If you have any ideas about new features or find any bugs, open an issue at [Issues tab](https://github.com/TheNooB2706/kdenlive-network-render/issues)

# License
[(Back to top)](#table-of-contents)

[GNU General Public License version 3](https://opensource.org/licenses/GPL-3.0)
