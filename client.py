import socket, sys, subprocess, shutil, os, argparse
from pathlib import Path
import xml.etree.ElementTree as ET

#Version string
__version__ = "1.0.0"
#argument parsing
parser = argparse.ArgumentParser(epilog="GitHub project page: https://github.com/TheNooB2706/kdenlive-network-render")
parser.add_argument("address", help = "IP address of server", type=str)
parser.add_argument("port", help = "Port of the server", type=int)
parser.add_argument("-b", "--melt-binary", help = "Path to the melt binary. Default to /usr/bin/melt", default = "/usr/bin/melt", type = Path)
parser.add_argument("-d", "--program-dir", help = "Path where this program use to store temporary files and mountpoint. Default to ~/.kdenlive_network_render", default = "~/.kdenlive_network_render", type = Path)
parser.add_argument("-l", "--local", help = "Start as local client where client and server are on the same machine.", action = "store_true")
parser.add_argument("-ssh", "--ssh-command", help = "Custom ssh command. Use for custom private key or ssh port etc.", type = str)
parser.add_argument("-t", "--threads", help = "Value of threads option in the .mlt file. Default to number of cpu cores.", default = os.cpu_count(), type=int)
parser.add_argument("-r", "--real-time", help = "The value of real_time option in the .mlt file. Default to -[number of cpu cores].", default = -(os.cpu_count()), type=int)
parser.add_argument("-x", "--use-xvfb", help = "Use xvfb as fake x11 server. Useful on headless server.", action = "store_true")
parser.add_argument("--no-cleanup", help = "If this option is set, the temporary files and folders created will not be deleted at exit.", action = "store_true")
parser.add_argument("--version", action="version", version=f"kdenlive-network-render {__version__}")
args = parser.parse_args()
if not args.melt_binary.exists():
    parser.error(f"{args.melt_binary} does not exist! Please specify valid path to MLT binary.")

#------------Functions---------
def modifymlt(mltfilepath, inf, outf):
    with open(mltfilepath, "r") as file:
        mltfilecontent = file.read()
    parsedmlt = ET.fromstring(mltfilecontent)
    fileformat = parsedmlt[1].attrib["f"]
    if parsedmlt.attrib["root"] != path.as_posix():
        parsedmlt.attrib["root"] = path.as_posix()
        parsedmlt[1].attrib["threads"] = str(args.threads)
        parsedmlt[1].attrib["real_time"] = str(args.real_time)
    parsedmlt[1].attrib["target"] = tempfolder.joinpath(constructfilename(inf, outf, fileformat)).as_posix()
    parsedmlt[1].attrib["in"] = str(inf)
    parsedmlt[1].attrib["out"] = str(outf)
    parsedmlt[1].attrib["an"] = "1"
    parsedmlt[1].attrib["audio_off"] = "1"
    savemlt = ET.tostring(parsedmlt, encoding="unicode")
    with open(mltfilepath, "w") as file:
        file.write(savemlt)

def getfileformat(mltfilepath):
    with open(mltfilepath, "r") as file:
        mltfilecontent = file.read()
    parsedmlt = ET.fromstring(mltfilecontent)
    fileformat = parsedmlt[1].attrib["f"]
    return fileformat

def renderfunc(meltbin, mltfile):
    print("-------------------------------")
    if args.use_xvfb:
        code = subprocess.call(["xvfb-run", "-a", meltbin, mltfile])
    else:
        code = subprocess.call([meltbin, mltfile])
    print("-------------------------------")
    return code

def constructfilename(inf, outf, fileformat):
    filename = f"{inf}-{outf}.{fileformat}"
    return filename

def doupload():
    print("-------------------------------")
    if args.ssh_command:
        code = subprocess.call(["rsync", "-aP", "-e", args.ssh_command, f"{tempfolder}{os.sep}", f"{serverusername}@{addr}:{mountdir}{os.sep}.kdenlive_network_render{os.sep}videos"])
    else:
        code = subprocess.call(["rsync", "-aP", f"{tempfolder}{os.sep}", f"{serverusername}@{addr}:{mountdir}{os.sep}.kdenlive_network_render{os.sep}videos"])
    print("-------------------------------")
    return code
#-------------------------------------
#----------variable and initialisation--------
maindir = args.program_dir.expanduser()
tempfolder = maindir.joinpath("temp")
path = maindir.joinpath("mount")
notlocal = not(args.local)

if path.is_mount() and notlocal:
    print("--------Unmounting previously mounted dir-------")
    if subprocess.call(["fusermount","-u",path]) == 0:
        print("Done")
    print("------------------------------------------------")

if notlocal:
    if not maindir.exists():
        maindir.mkdir()
    if not tempfolder.exists():
        tempfolder.mkdir()
    else:
        shutil.rmtree(tempfolder)
        tempfolder.mkdir()
    if not path.exists():
        path.mkdir()
    else:
        if not path.is_mount():
            shutil.rmtree(path)
            path.mkdir()
        else:
            print(f"Mountpoint {path} is mounted. Please unmount before continue.")
            sys.exit(1)

mltbinary = args.melt_binary.expanduser()
addr = args.address
port = args.port
s = socket.socket()
s.connect((addr, port))
initlist = s.recv(1024).decode().split(",")
mltfilename = initlist[0] #I have no idea why I declare this variable, but currently don't have time to look deeper, so it will stay now
serverusername = initlist[1]
mountdir = Path(initlist[2])
if not notlocal:
    tempfolder = mountdir.joinpath(".kdenlive_network_render/videos")
    path = mountdir
if notlocal:
    if args.ssh_command:
        subprocess.call(["sshfs", "-o", f"ssh_command={args.ssh_command}", f"{serverusername}@{addr}:{mountdir}", path])
    else:
        subprocess.call(["sshfs",f"{serverusername}@{addr}:{mountdir}", path]) #mounting sshfs
#------------------------------------
#---------Actually starting communication--------
ping = s.recv(128)
if ping.decode() == "ping":
    s.send(b"ready")
else:
    sys.exit(f"Command not recognised!: {ping.decode()}")
clientid = s.recv(128).decode()

jobreceived = []
s.send(b"standby")
while True:
    jobinout = s.recv(512).decode()
    if jobinout != "job done" and len(jobinout.split(",")) == 2:
        jobinout = jobinout.split(",")
        jobreceived.append(jobinout)
        modifymlt(path.joinpath(f".kdenlive_network_render/{clientid}.mlt"), jobinout[0], jobinout[1])
        executioncode = renderfunc(mltbinary, path.joinpath(f".kdenlive_network_render/{clientid}.mlt"))
        if executioncode == 0:
            sendstr = f"done,{jobinout[0]},{jobinout[1]}".encode()
            s.send(sendstr)
        else:
            sendstr = f"failed,{jobinout[0]},{jobinout[1]}".encode()
            s.send(sendstr)
            fileformat = getfileformat(path.joinpath(f".kdenlive_network_render/{clientid}.mlt"))
            subprocess.call(["rm",tempfolder.joinpath(constructfilename(jobinout[0], jobinout[1], fileformat))])
            jobreceived.remove(jobinout)
            print(f"Job {jobinout} failed!")
            input("Press Enter to continue (after checking the error manually)...")
            s.send(b"standby")
    else:
        break

received = s.recv(512).decode()
if received == "upload" and notlocal:
    exitcode = doupload()
    if exitcode == 0:
        s.send(b"done upload")
    else:
        s.send(b"error occurred")
        print("Error raised from last command.")
        input("Press Enter to continue...")
if not notlocal:
    s.send(b"done upload")

print("Client job done! Exitting...")

if notlocal:
    subprocess.call(["fusermount","-u",path])
    if (not args.no_cleanup) and (not path.is_mount()):
        shutil.rmtree(maindir)
