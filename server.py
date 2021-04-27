import socket, sys, subprocess, os, shutil, time, argparse
from pathlib import Path
import xml.etree.ElementTree as ET
from threading import Thread, Lock

parser = argparse.ArgumentParser()
parser.add_argument("port", help = "Port of the server", type=int)
parser.add_argument("mltfile", help = "Path to generated MLT project file.", type = Path)
parser.add_argument("-f", "--frame-split", help = "Set the number of frames to split into for each jobs. Default to 1000 frames.", type = int, default = 1000)
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
                print(f"Job {len(jobassigned)} of {len(joblist)} assigned.")
                print(f"Job {len(jobdone)} of {len(joblist)} done.\n")
        elif "done" in received.decode():
            job = [received.decode().split(",")[1], received.decode().split(",")[2]]
            jobdone.append(job)
            job = givejobfunc(joblist, jobassigned)
            if job:
                jobstr = f"{job[0]},{job[1]}".encode()
                sockobject.send(jobstr)
                jobassigned.append(job)
                print(f"Job {len(jobassigned)} of {len(joblist)} assigned.")
                print(f"Job {len(jobdone)} of {len(joblist)} done.\n")
        elif "failed" in received.decode():
            job = [received.decode().split(",")[1], received.decode().split(",")[2]]
            jobassigned.remove(job)
            print(f"Job {job} failed. Removing from assigned job. You might want to check for error at client from {client}")
        lock.release()
    if not failed:
        sockobject.send(b"job done")
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
    print("\n-----------------------------------")
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

with open(mltfilepath, "r") as file:
    mltfilecontent = file.read()
parsedmlt = ET.fromstring(mltfilecontent)
outputfile = Path(parsedmlt[1].attrib["target"])
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

print("\n---------Merging videos------------")
#-------------Concatenate videos----------------
videos = os.listdir(filetemp)
writecontent = ""
for i in videos:
    writecontent = writecontent + f"file '{i}'\n"
with open(filetemp.joinpath("concat.txt"), "w") as file:
    file.write(writecontent)
mergecode = subprocess.call(["ffmpeg", "-f", "concat", "-i", filetemp.joinpath("concat.txt"), "-c", "copy", "-map", "0:v", "-map", "0:a:0", outputfile])

if mergecode == 0:
    subprocess.call(["rm","client*.mlt"])
    shutil.rmtree(filetemp)
    print(f"File saved to {outputfile}.")
