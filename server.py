import socket, sys, subprocess, os, shutil, time, argparse, re
from pathlib import Path
import xml.etree.ElementTree as ET
from threading import Thread, Lock

#Version string
__version__ = "1.0.1"
#parsing argument
parser = argparse.ArgumentParser(epilog="GitHub project page: https://github.com/TheNooB2706/kdenlive-network-render")
parser.add_argument("port", help = "Port of the server", type=int)
parser.add_argument("mltfile", help = "Path to generated MLT project file.", type = Path)
parser.add_argument("-f", "--frame-split", help = "Set the number of frames to split into for each jobs. Default to 1000 frames.", type = int, default = 1000)
parser.add_argument("-b", "--melt-binary", help = "Path to the melt binary. Default to /usr/bin/melt", default = "/usr/bin/melt", type = Path)
parser.add_argument("--no-cleanup", help = "If this option is set, the temporary files and folders created will not be deleted at exit.", action = "store_true")
parser.add_argument("--verbose", "-v", help = "Enable verbose mode.", action = "store_true")
parser.add_argument("--version", action="version", version=f"kdenlive-network-render {__version__}")
args = parser.parse_args()
if not args.melt_binary.exists():
    parser.error(f"{args.melt_binary} does not exist! Please specify valid path to MLT binary.")
if not args.mltfile.exists():
    parser.error(f"{args.mlt} does not exist! Please specify valid path to .mlt file.")
#--------------Functions---------
def print_verbose(text):
    if args.verbose:
        print(text)

def printb(text):
    print(f"\033[1m{text}\033[0m")

def get_ip():
    import socket
    import fcntl
    import struct
    
    def ip_from_if(ifname):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return socket.inet_ntoa(fcntl.ioctl(
            s.fileno(),
            0x8915,  # SIOCGIFADDR
            struct.pack('256s', ifname[:15].encode('utf-8')))[20:24])

    ip = ""
    interface = [i[1] for i in socket.if_nameindex() if i[1] != "lo"] #get all interfaces except loopback
    for i in interface:
        try:
            address = ip_from_if(i)
            ip += f"{i}: {address} | "
        except OSError:
            continue
    return ip.strip(" | ")

def segregate(inf, outf):
    itern = int((outf - inf)/framesplit)+1
    joblist = []
    first = inf
    for i in range(itern):
        end = first+framesplit-1
        if end > outf:
            end = outf
        joblist.append([first, end])
        first += framesplit
    return joblist

def givejob(joblist, jobassigned):
    for i in joblist:
        if i not in jobassigned:
            return i
    return False

def constructfilename(inf, outf):
    filename = f"{inf}-{outf}"
    return filename

def threadfunc(sockobject, givejobfunc, joblist, jobassigned, jobdone, lock, client):
    failed = False
    while len(joblist) != len(jobdone):
        sockobject.settimeout(5)
        try:
            received = sockobject.recv(512)
        except socket.timeout:
            received = None
            continue
        lock.acquire()
        if received.decode() == "standby":
            job = givejobfunc(joblist, jobassigned)
            if job:
                jobstr = f"{job[0]},{job[1]}".encode()
                sockobject.send(jobstr)
                jobassigned.append(job)
                lastdone = len(jobdone)
                lasttime = time.time()
            print(f"\033[A{' '*getTermSize()[1]}\033[A")
            print(f"\033[A{' '*getTermSize()[1]}\033[A")
            print(f"{len(jobassigned)}/{len(joblist)} assigned|{len(jobdone)}/{len(joblist)} done")
            print(f"[{'='*(int(getTermSize()[1]*len(jobdone)/len(joblist))-2)}>")
        elif "done" in received.decode():
            job = [received.decode().split(",")[1], received.decode().split(",")[2]]
            jobdone.append(job)
            job = givejobfunc(joblist, jobassigned)
            deltatime = time.time() - lasttime
            deltadone = len(jobdone) - lastdone
            rate = deltatime/deltadone
            etaraw = rate * (len(joblist) - len(jobdone))
            etaparsed = format_seconds_to_hhmmss(etaraw)
            lasttime = time.time()
            lastdone = len(jobdone)
            if job:
                jobstr = f"{job[0]},{job[1]}".encode()
                sockobject.send(jobstr)
                jobassigned.append(job)
            print(f"\033[A{' '*getTermSize()[1]}\033[A")
            print(f"\033[A{' '*getTermSize()[1]}\033[A")
            print(f"{len(jobassigned)}/{len(joblist)} assigned|{len(jobdone)}/{len(joblist)} done|ETA={etaparsed}")
            print(f"[{'='*(int(getTermSize()[1]*len(jobdone)/len(joblist))-2)}>")
        elif "failed" in received.decode():
            job = [received.decode().split(",")[1], received.decode().split(",")[2]]
            jobassigned.remove(job)
            print(f"Job {job} failed. Removing from assigned job. You might want to check for error at client from {client}\n\n\n")
        lock.release()
    if not failed:
        sockobject.send(b"job done")
        time.sleep(1)

def getTermSize():
    rows, columns = os.popen("stty size","r").read().split()
    size=[]
    size.append(int(rows))
    size.append(int(columns))
    return size

def format_seconds_to_hhmmss(seconds):
    hours = seconds // (60*60)
    seconds %= (60*60)
    minutes = seconds // 60
    seconds %= 60
    return "%02i:%02i:%02i" % (hours, minutes, seconds)

def alphaNumOrder(string):
    """ Returns all numbers on 5 digits to let sort the  string with numeric order.
    Ex: alphaNumOrder("a6b12.125")  ==> "a00006b00012.00125"
    """
    return ''.join([format(int(x), '05d') if x.isdigit()
                   else x for x in re.split(r'(\d+)', string)])

def audioonlymlt(mltfilepath, filetemp):
    with open(mltfilepath, "r") as file:
        mltfilecontent = file.read()
    parsedmlt = ET.fromstring(mltfilecontent)
    vidformat = parsedmlt[1].attrib["f"]
    parsedmlt[1].attrib["target"] = filetemp.joinpath(f"audio.{vidformat}").as_posix()
    parsedmlt[1].attrib["vn"] = "1"
    parsedmlt[1].attrib["video_off"] = "1"
    savemlt = ET.tostring(parsedmlt, encoding="unicode")
    with open(mltfilepath, "w") as file:
        file.write(savemlt)

def renderaudio():
    audiomlt = filetemp.joinpath("audio.mlt")
    subprocess.run(["cp", mltfilepath, audiomlt], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    audioonlymlt(audiomlt, filetemp)
    audiocode = subprocess.run([args.melt_binary.expanduser(), audiomlt, "-quiet"]).returncode
    if audiocode != 0:
        input("Error occured when rendering audio. Please check the error and press Enter to continue.")
#---------------------------
#-------Variable and initialisation-----
framesplit = args.frame_split
port = args.port
mltfilepath = args.mltfile.expanduser()
with open(mltfilepath, "r") as file:
    mltfilecontent = file.read()
parsedmlt = ET.fromstring(mltfilecontent)
rootdir = Path(parsedmlt.attrib["root"])
filetemp = rootdir.joinpath(".kdenlive_network_render")
videofiletemp = filetemp.joinpath("videos")
if not filetemp.exists():
    filetemp.mkdir()
else:
    if any(filetemp.iterdir()):
        if input(f"Temporary directory {filetemp} not empty. Delete? [y/n]: ") != "y":
            sys.exit(f"Temporary directory {filetemp} not empty.")
    shutil.rmtree(filetemp)
    filetemp.mkdir()
videofiletemp.mkdir()

s = socket.socket()
s.bind(('', port))
s.listen()

clients = []

try:
    printb(f"Server listening on port {port}. Press Ctrl+C when all clients are connected.")
    print(get_ip())
    while True:
        client, addr = s.accept()
        print(f"client{len(clients)+1} from {addr} connected.")
        clients.append((client, addr))
        client.send(f"{mltfilepath.name},{os.getlogin()},{rootdir}".encode())
except KeyboardInterrupt:
    printb("\n-------------------------------")
    print("Stopped accepting connections. Initialising.")
    for i in clients:
        print_verbose(f"Pinging client{clients.index(i)+1} ......")
        i[0].send(b"ping")
        try:
            i[0].settimeout(5)
            response = i[0].recv(128)
            if response.decode() == "ready":
                print_verbose(f"client{clients.index(i)+1} ready.")
            else:
                print_verbose(f"client{clients.index(i)+1} not recognised. Removing...")
                clients.remove(i)
        except socket.timeout:
            print_verbose(f"client{clients.index(i)} timeout. Removing...")
            clients.remove(i)

printb("-------------------------------")
if len(clients) == 0:
    sys.exit("No client connected! Exitting...")
print(f"Total clients: {len(clients)}")
print("Clients list: ")
for i in clients:
    print(f"  client{clients.index(i)+1} from {i[1]}")
    i[0].send(f"client{clients.index(i)+1}".encode())
    subprocess.run(["cp", mltfilepath, filetemp.joinpath(f"client{clients.index(i)+1}.mlt")])
printb("-------------------------------")
input("Press Enter to continue...")
print("\n")

timestart = time.time()

outputfile = Path(parsedmlt[1].attrib["target"])
outputformat = parsedmlt[1].attrib["f"]
for i in parsedmlt.findall("consumer"):
    consumer = i
frames = [int(consumer.attrib["in"]), int(consumer.attrib["out"])]
joblist = segregate(frames[0], frames[1])
jobdone = []
jobassigned = []

threads = []
lock = Lock()
for i in clients:
    t = Thread(target = threadfunc, args=(i[0], givejob, joblist, jobassigned, jobdone, lock, i[1]))
    threads.append(t)
    t.start()
    
audiothread = Thread(target = renderaudio)
audiothread.start()
audiothread.join()

for i in threads:
    i.join()

print("All jobs done! Pinging clients to upload rendered jobs.")

for i in clients:
    i[0].send(b"upload")

print("Uploading...\n")

while True:
    received = os.listdir(videofiletemp)
    received = [i for i in received if i[0] != "."]
    uploaded = len(received)
    total = len(joblist)
    print(f"Progress: {uploaded}/{total}                     ", end = "\r")
    time.sleep(1)
    if uploaded == total:
        print("\n")
        break

for i in clients:
    status = i[0].recv(512).decode()
    if status == "done upload":
        print_verbose(f"Client from {i[1]} finished uploading.")
        continue
    else:
        print(f"Client from {i[1]} raised error when uploading")
        input("Press Enter to continue (after fixing the error manually of course)...")

#-------------Concatenate videos----------------
printb("\n---------Merging videos--------")
videos = os.listdir(videofiletemp)
videos.sort(key=alphaNumOrder)
writecontent = ""
for i in videos:
    writecontent = writecontent + f"file '{i}'\n"
with open(videofiletemp.joinpath("concat.txt"), "w") as file:
    file.write(writecontent)
mergecode = subprocess.run(["ffmpeg", "-hide_banner", "-f", "concat", "-i", videofiletemp.joinpath("concat.txt"), "-i", filetemp.joinpath(f"audio.{outputformat}"), "-c:v", "copy", "-c:a", "copy", outputfile]).returncode
if mergecode == 0:
    printb("--------Merge completed--------")
    if not args.no_cleanup:
        subprocess.run(["rm " + filetemp.joinpath("client*.mlt").as_posix()], shell = True)
        shutil.rmtree(filetemp)
    print(f"File saved to {outputfile}.")
else:
    input("Error occur when merging videos. Please check the error and press Enter to continue.")

print(f"Time elapsed: {format_seconds_to_hhmmss(time.time()-timestart)}")
