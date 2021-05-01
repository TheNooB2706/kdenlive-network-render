import socket, sys, subprocess, os, shutil, time, argparse, re
from pathlib import Path
import xml.etree.ElementTree as ET
from threading import Thread, Lock

parser = argparse.ArgumentParser()
parser.add_argument("port", help = "Port of the server", type=int)
parser.add_argument("mltfile", help = "Path to generated MLT project file.", type = Path)
parser.add_argument("-f", "--frame-split", help = "Set the number of frames to split into for each jobs. Default to 1000 frames.", type = int, default = 1000)
parser.add_argument("-b", "--melt-binary", help = "Path to the melt binary. Default to /bin/melt", default = "/bin/melt", type = Path)
args = parser.parse_args()

#--------------Functions---------
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
                print(f"{len(jobassigned)}/{len(joblist)} assigned|{len(jobdone)}/{len(joblist)} done")
                print(f"[{'='*(int(getTermSize()[1]*len(jobdone)/len(joblist))-2)}>")
        elif "done" in received.decode():
            print(f"\033[A{' '*getTermSize()[1]}\033[A")
            print(f"\033[A{' '*getTermSize()[1]}\033[A")
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
                print(f"{len(jobassigned)}/{len(joblist)} assigned|{len(jobdone)}/{len(joblist)} done|ETA={etaparsed}")
                print(f"[{'='*(int(getTermSize()[1]*len(jobdone)/len(joblist))-2)}>")
        elif "failed" in received.decode():
            job = [received.decode().split(",")[1], received.decode().split(",")[2]]
            jobassigned.remove(job)
            print(f"Job {job} failed. Removing from assigned job. You might want to check for error at client from {client}\n\n\n")
        lock.release()
    if not failed:
        sockobject.send(b"job done")

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
#---------------------------
#-------Variable and initialisation-----
framesplit = args.frame_split
port = args.port
mltfilepath = args.mltfile.expanduser()
filetemp = mltfilepath.parent.joinpath(".kdenlive_network_render")
if not filetemp.exists():
    filetemp.mkdir()
else:
    shutil.rmtree(filetemp)
    filetemp.mkdir()

s = socket.socket()
s.bind(('', port))
s.listen()

clients = []

try:
    print(f"Server listening on port {port}. Press Ctrl+C when all clients are connected.")
    while True:
        client, addr = s.accept()
        print(f"client{len(clients)+1} from {addr} connected.")
        clients.append((client, addr))
        client.send(f"{mltfilepath.name},{os.getlogin()},{mltfilepath.parent.as_posix()}".encode())
except KeyboardInterrupt:
    print("\n-------------------------------")
    print("Stopped accepting connections. Initialising.")
    for i in clients:
        print(f"Pinging client{clients.index(i)} ......")
        i[0].send(b"ping")
        try:
            i[0].settimeout(5)
            response = i[0].recv(128)
            if response.decode() == "ready":
                print(f"client{clients.index(i)+1} ready.")
            else:
                print(f"client{clients.index(i)+1} not recognised. Removing...")
                clients.remove(i)
        except socket.timeout:
            print(f"client{clients.index(i)} timeout. Removing...")
            clients.remove(i)

print("-------------------------------")
print(f"Total clients: {len(clients)}")
print("Clients list: ")
for i in clients:
    print(f"client{clients.index(i)+1} from {i[1]}")
    i[0].send(f"client{clients.index(i)+1}".encode())
    subprocess.call(["cp", mltfilepath, mltfilepath.parent.joinpath(f"client{clients.index(i)+1}.mlt")])
print("-------------------------------")
input("Press Enter to continue...")

timestart = time.time()

with open(mltfilepath, "r") as file:
    mltfilecontent = file.read()
parsedmlt = ET.fromstring(mltfilecontent)
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
    
for i in threads:
    i.join()

print("All jobs done! Pinging clients to upload rendered jobs.")

for i in clients:
    i[0].send(b"upload")

print("Uploading...\n")

while True:
    received = os.listdir(filetemp)
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
        print(f"Client from {i[1]} finished uploading.")
        continue
    else:
        print(f"Client from {i[1]} raised error when uploading")
        input("Press Enter to continue (after fixing the error manually of course)...")

print("\n---------Merging videos--------")
#-------------Concatenate videos----------------
videos = os.listdir(filetemp)
videos.sort(key=alphaNumOrder)
writecontent = ""
for i in videos:
    writecontent = writecontent + f"file '{i}'\n"
with open(filetemp.joinpath("concat.txt"), "w") as file:
    file.write(writecontent)
mergecode = subprocess.call(["ffmpeg", "-f", "concat", "-i", filetemp.joinpath("concat.txt"), "-vcodec", "copy", "-map", "0:v", filetemp.joinpath(f"video.{outputformat}"), "-y"])
if mergecode == 0:
    print("--------Merge completed--------")
else:
    input("Error occur when merging videos. Please check the error and press Enter to continue.")

#-------------Rendering audio------------
audiomlt = filetemp.joinpath("audio.mlt")
subprocess.call(["cp", mltfilepath, audiomlt])
audioonlymlt(audiomlt, filetemp)
print("---------Rendering audio----------")
audiocode = subprocess.call([args.melt_binary.expanduser(), audiomlt])
if audiocode == 0:
    print("-----Audio render completed----")
else:
    input("Error occured when rendering audio. Please check the error and press Enter to continue.")

#--------------Merge audio and video------------
print("----Merging audio and video----")
finalcode = subprocess.call(["ffmpeg", "-i", filetemp.joinpath(f"video.{outputformat}"), "-i", filetemp.joinpath(f"audio.{outputformat}"), "-c:v", "copy", "-c:a", "copy", outputfile])

if finalcode == 0:
    subprocess.call(["rm " + mltfilepath.parent.joinpath("client*.mlt").as_posix()], shell = True)
    #shutil.rmtree(filetemp)
    print(f"File saved to {outputfile}.")

print(f"Time elapsed: {format_seconds_to_hhmmss(time.time()-timestart)}")
