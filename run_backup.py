#!/bin/python

import time
import subprocess
import argparse
import sys
import os
from ordered_set import OrderedSet
from wakeonlan import send_magic_packet

StartTime = time.time()
verbosity = 0


def wakeupserver(mac, ip):
    if verbosity:
        print "Waking up Backup Server"

    wakeuptime = time.time()
    attempt = 0
    response = 1

    devnull = open(os.devnull, 'w')

    while response != 0:
        if verbosity > 1:
            print "Pinging server " + ip
        # Ping server to check if server up
        response = subprocess.call(["ping", "-c", "1", ip], stdout=devnull)
        if verbosity > 1:
            if response == 0:
                print "Server is up!"
                return True
        if time.time()-wakeuptime >= 120 or attempt == 0:  # If server dosen't respond after this time, consider the wakeup attempt failed
            if attempt > 3:
                print "Backup server did not respond in time. ABORT!"
                return False
            else:
                attempt += 1
                if verbosity and attempt > 1:
                    print "Server did not respond, try again. Attempt Nr " + str(attempt)
                wakeuptime = time.time()

                if verbosity > 1:
                    print "Sending magic packet to " + mac
                send_magic_packet(mac)
                if verbosity > 1:
                    print "Sending magic packet to " + mac
                send_magic_packet(mac)
                if verbosity > 1:
                    print "Sending magic packet to " + mac
                send_magic_packet(mac)
        time.sleep(10)

    time.sleep(60)  # Give the Server some Time to finish booting
    return True


def getsnapshots(dataset, ip, backuppool='', pool=''):
    if verbosity:
        if ip:
            print "Getting remote snapshots for dataset " + dataset
        else:
            print "Getting local snapshots for dataset " + dataset

    snapshots = []
    try:
        if ip:
            snaps = subprocess.check_output(["/bin/ssh", "-oStrictHostKeyChecking=no", "backup@" + str(ip),
                                            "/sbin/zfs list -H -r -t snapshot -o name -s creation -d 1 " + dataset])
        else:
            snaps = subprocess.check_output(["/sbin/zfs", "list", "-H", "-r", "-t", "snapshot", "-o", "name",
                                             "-s", "creation", "-d", "1", dataset])
        if 'no datasets available' not in snaps:
            for snapshot in snaps.splitlines():
                if 'snap_frequent' not in snapshot and 'snap_hourly' not in snapshot and 'auto-snap' in snapshot:
                    # I don't want frequent and hourly snapshots but also only auto snapshots
                    if backuppool:
                        # Changing poolname to local poolname for easier comparision later
                        snapshots.append(snapshot.replace(backuppool, pool, 1))
                    else:
                        snapshots.append(snapshot)
        else:
            print "no datasets available"
            raise ValueError
    except Exception as ex:
        if ip:
            print "Failed to retrieve remote snapshots"
        else:
            print "Failed to retrieve local snapshots"
        if verbosity:
            print ex
        sys.exit(1)

    return snapshots


def sendsnapshot(prevsnap, snap, ip, mem, port, backuppool, poolname):
    if 'nextdataset' in prevsnap:
        recvargs = ["/bin/ssh", "-oStrictHostKeyChecking=no", "backup@" + str(ip), "/bin/mbuffer -s 128k -m " + mem +
                    " -I " + port + " | /bin/sudo /sbin/zfs recv " +
                    backuppool + snap.split('@', 1)[0].replace(poolname, '', 1)]
        sendargs = ["/sbin/zfs", "send", snap]
        mbfrargs = ["/bin/mbuffer", "-s", "128k", "-m", mem, "-O", ip+":"+port]
    elif prevsnap:
        recvargs = ["/bin/ssh", "-oStrictHostKeyChecking=no", "backup@" + str(ip), "/bin/mbuffer -s 128k -m " + mem +
                    " -I " + port + " | /bin/sudo /sbin/zfs recv -F " +
                    backuppool + snap.split('@', 1)[0].replace(poolname, '', 1)]
        sendargs = ["/sbin/zfs", "send", "-i", prevsnap, snap]
        mbfrargs = ["/bin/mbuffer", "-s", "128k", "-m", mem, "-O", ip+":"+port]
    else:
        recvargs = ["/bin/ssh", "-oStrictHostKeyChecking=no", "backup@" + str(ip), "/bin/mbuffer -s 128k -m " + mem +
                    " -I " + port + " | /bin/sudo /sbin/zfs recv -F " +
                    backuppool + snap.split('@', 1)[0].replace(poolname, '', 1)]
        sendargs = ["/sbin/zfs", "send", snap]
        mbfrargs = ["/bin/mbuffer", "-s", "128k", "-m", mem, "-O", ip+":"+port]

    if verbosity > 2:
        print "recvargs:"
        print recvargs
        print "\n sendargs:"
        print sendargs
        print "\n mbfrargs:"
        print mbfrargs

    try:
        if verbosity > 1:
            print "Starting receiver"
        recv = subprocess.Popen(recvargs)
        time.sleep(2)
        if recv.poll() is None:  # Check if recv process is still there, else we wasting out time
            if verbosity > 1:
                print "Starting zfs send"
            send = subprocess.Popen(sendargs, stdout=subprocess.PIPE)
            if verbosity > 1:
                print "Starting sending mbuffer"
            mbuffer = subprocess.Popen(mbfrargs, stdin=send.stdout)
        else:
            print "Reciever failed"
            return False
    except subprocess.CalledProcessError as pe:
        print "Failed to send snapshot"
        if verbosity:
            print pe
        return False

    recv.wait()
    send.wait()
    mbuffer.wait()

    if recv.returncode != 0 or send.returncode != 0 or mbuffer.returncode != 0:
        print "Failed to send Snapshot"
        print "recv rcode=" + str(recv.returncode) + " send rcode=" + str(send.returncode)\
              + " mbuffer rcode=" + str(mbuffer.returncode)
        return False

    return True


def main():
    global verbosity

    # Define and read args

    argp = argparse.ArgumentParser(description='Runs backup to backup sever')
    argp.add_argument('mac', type=str, help='MAC address of Backup server')
    argp.add_argument('ip', type=str, help="IP address of backup Server")
    argp.add_argument('mem', type=str, help="Memory to allocate for mbuffer")
    argp.add_argument('port', type=str, help="Port to use by for mbuffer")
    argp.add_argument('backuppool', type=str, help="Remote pool to backup to")
    argp.add_argument('-v', '--verbosity', type=int, help="Increase output verbosity")
    argp.add_argument('-i', '--initbackup', action='store_true', help="initial backup")  # https://docs.oracle.com/cd/E19253-01/819-5461/gbinw/index.html
    argp.add_argument('-p', '--poweroff', action='store_true', help="Shut down remote system after backup")
    args = argp.parse_args()

    if args.verbosity:
        print("Verbosity turned on")

    verbosity = args.verbosity

    if not wakeupserver(args.mac, args.ip):
        print "wakeup failed"
        sys.exit(1)

    datasets = []

    try:
        sets = subprocess.check_output(["/sbin/zfs", "list", "-H", "-o", "name"])
        for dataset in sets.splitlines():
                datasets.append(dataset)
    except Exception as ex:
        print "Failed to retrieve local datasets"
        if verbosity:
            print ex
        sys.exit(1)

    pool = datasets[0]

    for dataset in datasets:
        if verbosity > 1:
            print "Processing dataset " + dataset
        if args.initbackup:
            if verbosity:
                print "initbackup"
            prevsnap = ''  # We don't have a snapshot to refer to for initial backup
            for snap in getsnapshots(dataset, 0):
                if verbosity > 1:
                    print "Sending snapshot " + snap
                    if not sendsnapshot(prevsnap, snap, args.ip, args.mem, args.port, args.backuppool, pool):
                        print "Error while sending snapshot "
                        sys.exit(1)
                prevsnap = snap
            prevsnap = 'nextdataset'  # We cannot start an incremental send with a snapshot from another dataset
        else:
            localsnapshots = getsnapshots(dataset, 0)
            remotesnapshots = getsnapshots(args.backuppool+dataset.replace(pool, '', 1), args.ip, args.backuppool, pool)

            transfersnapshots = list(OrderedSet(localsnapshots) - OrderedSet(remotesnapshots))
            deletesnapshots = list(OrderedSet(remotesnapshots) - OrderedSet(localsnapshots))

            if not transfersnapshots and not deletesnapshots:
                print "Remote dataset already up-to-date"
                continue

            prevsnap = str(remotesnapshots[-1])

            if prevsnap not in localsnapshots:
                print "No reference snapshot available"
                sys.exit(1)

            if verbosity > 1:
                if transfersnapshots:
                    print "Snapshots to send:"
                    print transfersnapshots
                if deletesnapshots:
                    print "Snapshots to remove from remote:"
                    print deletesnapshots
                if transfersnapshots:
                    print "Referencing incremental send on " + prevsnap

            for snap in transfersnapshots:
                if verbosity:
                    print "Sending snapshot " + snap
                    if not sendsnapshot(prevsnap, snap, args.ip, args.mem, args.port, args.backuppool, pool):
                        print "Error while sending snapshot "
                        sys.exit(1)
                    prevsnap = snap

            for snap in deletesnapshots:
                if verbosity:
                    print "Removing snapshot " + snap + " from remote system"
                    try:
                        remove = subprocess.check_call(["/bin/ssh", "-oStrictHostKeyChecking=no", "backup@"
                                                        + str(args.ip), "/bin/sudo /sbin/zfs destroy " +
                                                        snap.replace(pool, args.backuppool, 1)])
                    except subprocess.CalledProcessError as pe:
                        print "Failed to remove remote snapshot"
                        if verbosity:
                            print pe

        if verbosity:
            print "Replication complete"

        if args.poweroff:
            if verbosity:
                print "Shutting down remote system"
            try:
                subprocess.call(["/bin/ssh", "-oStrictHostKeyChecking=no", "backup@" + str(args.ip),
                                 "/bin/sudo /sbin/init 0"])
            except subprocess.CalledProcessError as pe:
                print "Failed to shut down remote system"
                if verbosity:
                    print pe


if __name__ == '__main__':
    main()
